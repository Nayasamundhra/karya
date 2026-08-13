"""GET /api/v1/auth/me (spec checks 21-25)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Tenant, User, UserRole, UserStatus
from tests.conftest import auth_header

ME_URL = "/api/v1/auth/me"


# ---------------------------------------------------------------------------
# 21. Happy path
# ---------------------------------------------------------------------------


def test_me_returns_the_authenticated_user(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user = user_factory(
        tenant,
        email="rahul@acme.com",
        employee_code="EMP-042",
        name="Rahul Sharma",
        role=UserRole.MANAGER,
    )
    token = login("acme", "rahul@acme.com").json()["access_token"]

    response = client.get(ME_URL, headers=auth_header(token))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "tenant_id": str(tenant.id),
        "employee_code": "EMP-042",
        "name": "Rahul Sharma",
        "email": "rahul@acme.com",
        "role": "MANAGER",
        "status": "ACTIVE",
    }


# ---------------------------------------------------------------------------
# 22. Authentication required
# ---------------------------------------------------------------------------


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_malformed_authorization_headers(client: TestClient) -> None:
    for header in (
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer not.a.jwt"},
        {"Authorization": ""},
    ):
        response = client.get(ME_URL, headers=header)
        assert response.status_code == 401, header


def test_me_rejects_a_token_for_a_deleted_user(client: TestClient) -> None:
    """A validly signed token whose subject no longer exists must 401."""
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "SUPER_ADMIN",
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    assert client.get(ME_URL, headers=auth_header(token)).status_code == 401


def test_me_rejects_a_refresh_token_used_as_a_bearer_credential(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    refresh_token = login("acme", "rahul@acme.com").json()["refresh_token"]

    response = client.get(ME_URL, headers=auth_header(refresh_token))

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 23. Identity comes only from the token
# ---------------------------------------------------------------------------


def test_me_ignores_a_client_supplied_user_id(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Query params, body and headers must not influence who is returned."""
    tenant = tenant_factory(slug="acme")
    caller = user_factory(tenant, email="rahul@acme.com", employee_code="A-1")
    victim = user_factory(tenant, email="priya@acme.com", employee_code="A-2")
    token = login("acme", "rahul@acme.com").json()["access_token"]

    attempts = [
        client.get(
            ME_URL, params={"user_id": str(victim.id)}, headers=auth_header(token)
        ),
        client.get(
            ME_URL,
            params={"sub": str(victim.id), "role": "SUPER_ADMIN"},
            headers=auth_header(token),
        ),
        client.request(
            "GET",
            ME_URL,
            json={"user_id": str(victim.id)},
            headers=auth_header(token),
        ),
        client.get(
            ME_URL,
            headers={**auth_header(token), "X-User-Id": str(victim.id)},
        ),
    ]

    for response in attempts:
        assert response.status_code == 200
        assert response.json()["id"] == str(caller.id)
        assert response.json()["id"] != str(victim.id)


# ---------------------------------------------------------------------------
# 24. No credential leakage
# ---------------------------------------------------------------------------


def test_me_never_exposes_password_hash(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]

    response = client.get(ME_URL, headers=auth_header(token))
    body = response.json()

    assert "password_hash" not in body
    assert "password" not in body
    # Nothing resembling the stored Argon2 hash appears anywhere in the payload.
    assert "$argon2" not in response.text
    assert user.password_hash is not None
    assert user.password_hash not in response.text
    assert set(body) == {
        "id",
        "tenant_id",
        "employee_code",
        "name",
        "email",
        "role",
        "status",
    }


# ---------------------------------------------------------------------------
# 25. Database is authoritative for status
# ---------------------------------------------------------------------------


def test_deactivated_user_loses_access_immediately(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """A token issued while active must stop working the moment status changes."""
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com")
    token = login("acme", "rahul@acme.com").json()["access_token"]

    assert client.get(ME_URL, headers=auth_header(token)).status_code == 200

    user.status = UserStatus.INACTIVE.value
    db_session.flush()

    # Same still-unexpired token, now refused - the DB, not the token, decides.
    assert client.get(ME_URL, headers=auth_header(token)).status_code == 401


def test_role_change_takes_effect_without_a_new_token(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """/me reports the database role, not the role baked into the token."""
    tenant = tenant_factory(slug="acme")
    user = user_factory(tenant, email="rahul@acme.com", role=UserRole.STAFF)
    token = login("acme", "rahul@acme.com").json()["access_token"]

    assert client.get(ME_URL, headers=auth_header(token)).json()["role"] == "STAFF"

    user.role = UserRole.MANAGER.value
    db_session.flush()

    assert client.get(ME_URL, headers=auth_header(token)).json()["role"] == "MANAGER"
