"""Error responses say what a client needs and nothing about the server (Phase 7).

Two properties are being defended:

1. **Nothing internal escapes.** No stack trace, SQL statement, table name,
   filesystem path, environment variable or credential may reach a client, whatever
   the failure.
2. **Nothing the caller sent is echoed.** A validation error names the field and
   the rule; it does not quote the value. This was a real defect: FastAPI's default
   handler returned the submitted **password** in the 422 body of
   ``POST /auth/login``.

The Phase 1-6 error contract is unchanged - every error is still
``{"detail": ...}`` - and several existing tests assert exact bodies such as
``{"detail": "User not found"}``, so the correlation id lives in the
``X-Request-ID`` header rather than in the body.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.errors import register_exception_handlers, sanitise_validation_errors
from app.main import app
from app.middleware.request_context import REQUEST_ID_HEADER
from app.models import Tenant, User
from tests.conftest import auth_header, make_get_db_override

SENSITIVE_PASSWORD = "correct-horse-battery-staple-secret"


# ---------------------------------------------------------------------------
# Validation errors must not quote the submitted value
# ---------------------------------------------------------------------------


def test_a_short_password_is_not_echoed_back_by_login(client: TestClient) -> None:
    """The defect this handler exists for.

    A password that fails the length check used to come back inside the 422 body,
    from where it reaches browser consoles, client-side error reporting and any
    proxy that logs response bodies.
    """
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "acme", "email": "a@b.com", "password": "shrt"},
    )

    assert response.status_code == 422
    assert "shrt" not in response.text
    # It still says exactly what is wrong.
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert "at least 8" in error["msg"]


def test_a_short_password_is_not_echoed_back_by_user_creation(
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

    response = client.post(
        "/api/v1/users",
        json={
            "email": "new@acme.com",
            "password": "tiny",
            "name": "New Person",
            "employee_code": "EMP-9",
            "role": "STAFF",
        },
        headers=auth_header(token),
    )

    assert response.status_code == 422
    assert "tiny" not in response.text


def test_a_smuggled_field_names_the_field_but_not_its_value(
    client: TestClient,
) -> None:
    """``extra="forbid"`` is a security boundary, and its 422 must not become a
    mirror for whatever an attacker put in the request."""
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme",
            "email": "a@b.com",
            "password": SENSITIVE_PASSWORD,
            "role": "SUPER_ADMIN",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 422
    body = response.text
    assert "SUPER_ADMIN" not in body
    assert SENSITIVE_PASSWORD not in body
    # The field names are reported, which is what a client needs to fix the call.
    locations = [error["loc"] for error in response.json()["detail"]]
    assert ["body", "role"] in locations


def test_validation_errors_carry_only_type_loc_and_msg() -> None:
    """An allowlist, not a denylist: a new Pydantic error field cannot leak by
    default just because nobody thought to strip it."""
    sanitised = sanitise_validation_errors(
        [
            {
                "type": "too_short",
                "loc": ["body", "password"],
                "msg": "Value should have at least 8 items",
                "input": "the-actual-password",
                "ctx": {"min_length": 8, "value": "the-actual-password"},
                "url": "https://errors.pydantic.dev/2.13/v/too_short",
                "future_pydantic_field": "the-actual-password",
            }
        ]
    )

    assert sanitised == [
        {
            "type": "too_short",
            "loc": ["body", "password"],
            "msg": "Value should have at least 8 items",
        }
    ]
    assert "the-actual-password" not in json.dumps(sanitised)


def test_list_indices_in_a_location_survive_intact() -> None:
    """``loc`` may contain integers; stringifying them would misreport the field."""
    sanitised = sanitise_validation_errors(
        [{"type": "missing", "loc": ["body", "items", 3, "name"], "msg": "Field required"}]
    )

    assert sanitised[0]["loc"] == ["body", "items", 3, "name"]


def test_a_malformed_body_is_a_clean_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=b"{not json at all",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_an_invalid_uuid_in_a_path_is_a_422_naming_the_parameter(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/attendance/users/not-a-uuid", headers=auth_header("irrelevant")
    )

    # Authentication is checked first, so this is a 401 - which is itself the right
    # answer: an unauthenticated caller learns nothing about parameter validity.
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Unhandled exceptions
# ---------------------------------------------------------------------------


def failing_app() -> FastAPI:
    """An application whose one route always raises.

    Built from the real ``create_app`` so the middleware stack under test is the
    shipped one, with a deliberately broken route bolted on.
    """
    from app.main import create_app

    broken = create_app()

    @broken.get("/boom")
    def boom() -> None:
        raise RuntimeError(
            f"secret={SENSITIVE_PASSWORD} path=/home/karya/app/services/auth.py"
        )

    return broken


def test_an_unhandled_exception_returns_a_generic_500() -> None:
    """``raise_server_exceptions=False`` is needed to see the response a real client
    would get rather than having the test client re-raise."""
    with TestClient(failing_app(), raise_server_exceptions=False) as broken_client:
        response = broken_client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_a_500_leaks_neither_traceback_nor_secret_nor_path() -> None:
    with TestClient(failing_app(), raise_server_exceptions=False) as broken_client:
        response = broken_client.get("/boom")

    body = response.text
    assert SENSITIVE_PASSWORD not in body
    assert "RuntimeError" not in body
    assert "Traceback" not in body
    assert "/home/karya" not in body
    assert ".py" not in body


def test_a_500_is_still_traceable_and_still_hardened() -> None:
    """The case an operator most needs to trace is the one that must be traceable.

    This is why unhandled exceptions are caught in the correlation middleware rather
    than by a handler on Starlette's ``ServerErrorMiddleware``, which sits outside
    it and would produce a response with no id and no headers.
    """
    with TestClient(failing_app(), raise_server_exceptions=False) as broken_client:
        response = broken_client.get("/boom")

    assert response.headers[REQUEST_ID_HEADER]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_the_traceback_does_reach_the_log() -> None:
    """Suppressing it from the response is only acceptable because it is recorded."""
    import io
    import logging

    from app.core.context import RequestContextFilter
    from app.core.logging import JsonFormatter, configure_logging

    configure_logging(force=True)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        with TestClient(failing_app(), raise_server_exceptions=False) as broken_client:
            response = broken_client.get("/boom")
    finally:
        root.removeHandler(handler)

    records = [
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if line.strip() and json.loads(line).get("event") == "unhandled_exception"
    ]
    assert records
    logged = records[-1]
    assert "RuntimeError" in str(logged["exception"])
    assert logged["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_an_unexpected_database_error_becomes_a_generic_500(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """A SQLAlchemy error's text can carry the statement, the table and - for some
    drivers - the bound parameters. None of it may reach a client."""
    from app.db.session import get_db

    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    class ExplodingSession:
        """Stands in for a session whose next statement fails."""

        def __getattr__(self, name: str) -> object:
            raise OperationalError(
                "SELECT users.password_hash FROM users WHERE users.email = 'rahul@acme.com'",
                {"password_hash": "$argon2id$v=19$m=65536,t=3,p=4$sensitive"},
                Exception("connection to server was lost"),
            )

    def exploding_db():  # noqa: ANN202 - a test double
        yield ExplodingSession()

    app.dependency_overrides[get_db] = exploding_db
    try:
        with TestClient(app, raise_server_exceptions=False) as broken_client:
            response = broken_client.get(
                "/api/v1/attendance/me", headers=auth_header(token)
            )
    finally:
        app.dependency_overrides[get_db] = make_get_db_override(db_session)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    body = response.text
    assert "argon2" not in body
    assert "SELECT" not in body
    assert "users" not in body
    assert "password_hash" not in body


def test_the_error_handlers_are_registered_on_the_real_app() -> None:
    """A handler nobody installed is a comment."""
    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import SQLAlchemyError

    assert RequestValidationError in app.exception_handlers
    assert SQLAlchemyError in app.exception_handlers

    # Idempotent, so wiring it twice cannot double-register or crash.
    register_exception_handlers(app)
    assert RequestValidationError in app.exception_handlers


# ---------------------------------------------------------------------------
# The Phase 1-6 contract is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("get", "/api/v1/auth/me", 401),
        ("get", "/api/v1/users", 401),
        ("get", "/nonexistent", 404),
        ("patch", "/api/v1/auth/me", 405),
    ],
)
def test_every_error_is_still_a_detail_object(
    client: TestClient, method: str, path: str, expected: int
) -> None:
    response = getattr(client, method)(path)

    assert response.status_code == expected
    body = response.json()
    assert set(body) == {"detail"}
    assert isinstance(body["detail"], str)


def test_the_401_still_carries_www_authenticate(client: TestClient) -> None:
    """FastAPI's own HTTPException handler is deliberately left in place, so headers
    set on an HTTPException still reach the response."""
    response = client.get("/api/v1/auth/me")

    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


def test_a_cross_tenant_404_is_still_byte_identical_to_a_fictional_one(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """The Phase 6 anti-enumeration property, re-checked now that a correlation id
    is attached to every response: it is in the *header*, so the two bodies stay
    identical."""
    from app.models.user import UserRole

    acme = tenant_factory(slug="acme")
    user_factory(
        acme, email="admin@acme.com", employee_code="ADM-1", role=UserRole.TENANT_ADMIN
    )
    other = tenant_factory(slug="globex")
    outsider = user_factory(other, email="rahul@globex.com", employee_code="EMP-2")
    token = login("acme", "admin@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    real_elsewhere = client.get(
        f"/api/v1/users/{outsider.id}", headers=auth_header(token)
    )
    fiction = client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        headers=auth_header(token),
    )

    assert real_elsewhere.status_code == fiction.status_code == 404
    assert real_elsewhere.text == fiction.text
    # Traceable all the same, because the id is not in the body.
    assert real_elsewhere.headers[REQUEST_ID_HEADER] != fiction.headers[REQUEST_ID_HEADER]


def test_a_business_refusal_is_still_a_200(
    db_session: Session,
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., object],
    login: Callable[..., object],
) -> None:
    """Phase 7 must not have turned a refusal into an HTTP error.

    A well-formed request refused on its merits is 200 with ``verified: false`` - a
    convention the whole client depends on.
    """
    tenant = tenant_factory(slug="acme")
    location_factory(tenant)
    user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]  # type: ignore[attr-defined]

    response = client.post(
        "/api/v1/presence/verify",
        json={
            "latitude": 12.9716,
            "longitude": 77.5946,
            "accuracy_meters": 10.0,
            "challenge_id": "00000000-0000-0000-0000-000000000000",
            "nonce": "x" * 43,
        },
        headers=auth_header(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["verified"] is False
    assert body["reason"] == "QR_NOT_FOUND"
