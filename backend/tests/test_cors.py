"""CORS: exactly the configured origins, and no others (Phase 7).

CORS is the browser's only defence against a malicious page reading a Karya
response using the visitor's own credentials, so "which origins are allowed" is a
security decision and is tested as one. Every test here builds its own application
from an explicit configuration rather than depending on whatever the developer
happens to have in ``.env``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.middleware.request_context import REQUEST_ID_HEADER

GOOD_SECRET = "a-sufficiently-long-test-secret-key-1234"
ALLOWED = "https://app.karya.io"
DISALLOWED = "https://evil.example.com"

ALLOW_ORIGIN = "access-control-allow-origin"
ALLOW_CREDENTIALS = "access-control-allow-credentials"


def settings_for(**overrides: object) -> Settings:
    base: dict[str, object] = {"environment": "local", "jwt_secret_key": GOOD_SECRET}
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def client_allowing(origins: str) -> TestClient:
    return TestClient(create_app(settings_for(cors_allowed_origins=origins)))


@pytest.fixture
def cors_client() -> TestClient:
    return client_allowing(f"{ALLOWED},http://localhost:5173")


# ---------------------------------------------------------------------------
# Allowed and disallowed origins
# ---------------------------------------------------------------------------


def test_an_allowed_origin_is_granted_credentialed_access(
    cors_client: TestClient,
) -> None:
    response = cors_client.get("/health", headers={"Origin": ALLOWED})

    assert response.status_code == 200
    # Echoed exactly, never as a wildcard - a wildcard is invalid with credentials.
    assert response.headers[ALLOW_ORIGIN] == ALLOWED
    assert response.headers[ALLOW_CREDENTIALS] == "true"


def test_a_disallowed_origin_gets_no_permission(cors_client: TestClient) -> None:
    """The request still succeeds; the *browser* is what refuses to hand the body
    over, and it refuses because no ``Access-Control-Allow-Origin`` came back."""
    response = cors_client.get("/health", headers={"Origin": DISALLOWED})

    assert response.status_code == 200
    assert ALLOW_ORIGIN not in response.headers


def test_a_near_miss_origin_is_not_allowed(cors_client: TestClient) -> None:
    """Matching is exact: scheme, host and port all count.

    These are the shapes an attacker registers - a lookalike subdomain, a bare
    parent domain, the same host over http.
    """
    for origin in (
        "https://app.karya.io.evil.example.com",
        "https://karya.io",
        "http://app.karya.io",
        "https://app.karya.io:8443",
        "https://APP.KARYA.IO",
    ):
        response = cors_client.get("/health", headers={"Origin": origin})
        assert ALLOW_ORIGIN not in response.headers, origin


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------


def test_preflight_from_an_allowed_origin_is_approved(cors_client: TestClient) -> None:
    response = cors_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers[ALLOW_ORIGIN] == ALLOWED
    allowed_methods = response.headers["access-control-allow-methods"]
    assert "POST" in allowed_methods and "PATCH" in allowed_methods


def test_preflight_from_a_disallowed_origin_is_refused(
    cors_client: TestClient,
) -> None:
    response = cors_client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": DISALLOWED,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert ALLOW_ORIGIN not in response.headers


def test_a_preflight_still_gets_security_headers_and_a_request_id(
    cors_client: TestClient,
) -> None:
    """CORS is mounted inside the header and correlation middleware, so even a
    response CORS generates by itself is hardened and traceable."""
    response = cors_client.options(
        "/api/v1/auth/login",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers[REQUEST_ID_HEADER]


# ---------------------------------------------------------------------------
# The default and the wildcard
# ---------------------------------------------------------------------------


def test_no_configured_origins_means_no_cors_at_all() -> None:
    """The safe default for a backend with no browser client.

    The middleware is not installed, so no ``Access-Control-*`` header exists to be
    got wrong.
    """
    with client_allowing("") as bare:
        response = bare.get("/health", headers={"Origin": ALLOWED})

        assert response.status_code == 200
        assert ALLOW_ORIGIN not in response.headers
        assert (
            bare.options(
                "/api/v1/auth/login",
                headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
            ).status_code
            == 405
        )


def test_a_wildcard_origin_cannot_be_configured() -> None:
    """Rejected at startup, so there is no runtime path where it could apply.

    With credentials a wildcard is both forbidden by the CORS spec and a hole: it
    would let any page on the internet read authenticated responses.
    """
    with pytest.raises(ValidationError):
        settings_for(cors_allowed_origins="*")
    with pytest.raises(ValidationError):
        settings_for(cors_allowed_origins=f"{ALLOWED},*")


# ---------------------------------------------------------------------------
# What a frontend needs to be able to read
# ---------------------------------------------------------------------------


def test_the_correlation_id_is_exposed_to_the_browser(
    cors_client: TestClient,
) -> None:
    """A header a browser cannot read is useless to the client that would report it.

    ``Retry-After`` is exposed for the same reason: a frontend that cannot read it
    cannot back off correctly on a 429.
    """
    exposed = cors_client.get("/health", headers={"Origin": ALLOWED}).headers[
        "access-control-expose-headers"
    ]

    assert REQUEST_ID_HEADER.lower() in exposed.lower()
    assert "retry-after" in exposed.lower()
