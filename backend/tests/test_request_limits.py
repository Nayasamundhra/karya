"""Request size limits (Phase 7).

Size is checked at the ASGI boundary because Pydantic cannot help: by the time a
schema is applied the body has been received and JSON-decoded, which is where a
multi-megabyte payload costs memory and CPU.

The important pair of properties: an oversized request is refused **before** it is
parsed, and a normal request is entirely unaffected. The second half is what stops
this being a limit that quietly breaks the product.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.main import create_app
from app.models import Tenant, User
from app.services.attendance import queries as attendance_queries
from app.services.users import service as users_service
from tests.conftest import auth_header

GOOD_SECRET = "a-sufficiently-long-test-secret-key-1234"
JSON = {"Content-Type": "application/json"}


def settings_for(**overrides: object) -> Settings:
    base: dict[str, object] = {"environment": "local", "jwt_secret_key": GOOD_SECRET}
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Body size
# ---------------------------------------------------------------------------


def test_an_oversized_declared_body_is_refused(client: TestClient) -> None:
    oversized = b'{"x":"' + b"a" * (settings.max_request_body_bytes + 1) + b'"}'

    response = client.post("/api/v1/auth/login", content=oversized, headers=JSON)

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_a_body_at_the_limit_is_accepted(client: TestClient) -> None:
    """The boundary is inclusive, so a payload of exactly the limit gets through to
    validation - which is where it is then rejected on its merits, as a 422."""
    filler = settings.max_request_body_bytes - len('{"tenant_slug":""}')
    at_limit = b'{"tenant_slug":"' + b"a" * filler + b'"}'
    assert len(at_limit) == settings.max_request_body_bytes

    response = client.post("/api/v1/auth/login", content=at_limit, headers=JSON)

    assert response.status_code == 422


def test_a_streamed_body_cannot_evade_the_limit(client: TestClient) -> None:
    """Trusting ``Content-Length`` alone would be a hole: a client may simply omit
    it and send chunked. So the body is counted as it arrives."""

    def chunks():  # noqa: ANN202 - a generator makes httpx use chunked encoding
        for _ in range(20):
            yield b"a" * 8_192

    response = client.post("/api/v1/auth/login", content=chunks(), headers=JSON)

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


def test_a_lying_content_length_does_not_help(client: TestClient) -> None:
    """A declared length under the limit does not license a body over it."""
    body = b"a" * (settings.max_request_body_bytes + 1_000)

    response = client.post(
        "/api/v1/auth/login",
        content=body,
        headers={**JSON, "Content-Length": str(len(body))},
    )

    assert response.status_code == 413


def test_the_body_limit_is_configurable() -> None:
    tiny = create_app(settings_for(max_request_body_bytes=50))

    with TestClient(tiny) as tiny_client:
        assert (
            tiny_client.post(
                "/api/v1/auth/login", content=b"a" * 100, headers=JSON
            ).status_code
            == 413
        )
        # Under the tiny limit, so it reaches validation.
        assert (
            tiny_client.post(
                "/api/v1/auth/login", content=b'{"a":1}', headers=JSON
            ).status_code
            == 422
        )


def test_a_normal_request_is_unaffected(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """The half of the limit that matters most: real traffic must not notice it."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme",
            "email": "rahul@acme.com",
            "password": "correct-horse-battery-staple",
        },
    )

    assert response.status_code == 200


def test_the_limit_is_generous_next_to_the_largest_real_payload() -> None:
    """A presence verification is Karya's biggest body and it is a few hundred bytes.

    Stated as an assertion so that shrinking the limit into the range of real traffic
    fails here rather than in production.
    """
    largest_realistic = len(
        '{"latitude":12.9716,"longitude":77.5946,"accuracy_meters":12.5,'
        '"challenge_id":"00000000-0000-0000-0000-000000000000",'
        '"nonce":"' + "x" * 43 + '"}'
    )

    assert settings.max_request_body_bytes > largest_realistic * 50


# ---------------------------------------------------------------------------
# Query string size
# ---------------------------------------------------------------------------


def test_an_overlong_query_string_is_refused(client: TestClient) -> None:
    """Cheap to send, and unlike a body it ends up in access logs and proxy caches."""
    response = client.get("/health?q=" + "a" * (settings.max_query_string_bytes + 1))

    assert response.status_code == 414
    assert response.json() == {"detail": "Query string too long"}


def test_a_realistic_query_string_is_accepted(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """The longest legitimate query Karya accepts: a maximum-length search term
    plus every filter and pagination parameter at once."""
    from app.models.user import UserRole

    tenant = tenant_factory(slug="acme")
    user_factory(
        tenant, email="admin@acme.com", employee_code="ADM-1", role=UserRole.TENANT_ADMIN
    )
    token = login("acme", "admin@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    response = client.get(
        f"/api/v1/users?search={'a' * 255}&role=STAFF&status=ACTIVE"
        f"&page=1&page_size={users_service.MAX_PAGE_SIZE}",
        headers=auth_header(token),
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# The existing bounds are still enforced
# ---------------------------------------------------------------------------


def test_pagination_and_range_caps_are_unchanged() -> None:
    """Phase 7 adds limits; it must not have relaxed the Phase 5/6 ones."""
    assert attendance_queries.MAX_PAGE_SIZE == 100
    assert attendance_queries.DEFAULT_PAGE_SIZE == 30
    assert attendance_queries.MAX_RANGE_DAYS == 366
    assert users_service.MAX_PAGE_SIZE >= 1
    assert users_service.DEFAULT_PAGE_SIZE <= users_service.MAX_PAGE_SIZE


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("page_size=1000", 422),
        ("page_size=0", 422),
        ("page=0", 422),
        ("page=-1", 422),
        ("from_date=2020-01-01&to_date=2026-12-31", 422),
        ("from_date=2026-12-31&to_date=2026-01-01", 422),
    ],
)
def test_read_endpoints_still_refuse_unbounded_requests(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
    query: str,
    expected: int,
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    response = client.get(
        f"/api/v1/attendance/me/history?{query}", headers=auth_header(token)
    )

    assert response.status_code == expected


def test_a_search_term_is_still_length_capped(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    from app.models.user import UserRole

    tenant = tenant_factory(slug="acme")
    user_factory(
        tenant, email="admin@acme.com", employee_code="ADM-1", role=UserRole.TENANT_ADMIN
    )
    token = login("acme", "admin@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    response = client.get(
        f"/api/v1/users?search={'a' * 256}", headers=auth_header(token)
    )

    assert response.status_code == 422
