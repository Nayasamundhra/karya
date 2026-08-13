"""POST /api/v1/auth/login (spec checks 5-12)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RefreshToken, Tenant, User, UserStatus
from tests.conftest import DEFAULT_PASSWORD

LOGIN_URL = "/api/v1/auth/login"

#: The single message every credential failure must return.
GENERIC_ERROR = "Invalid credentials"


# ---------------------------------------------------------------------------
# 5. Happy path
# ---------------------------------------------------------------------------


def test_valid_user_can_log_in(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = login("acme", "rahul@acme.com")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]
    # No credential material comes back beyond the tokens themselves.
    assert set(body) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert "password_hash" not in response.text


def test_login_persists_only_a_refresh_token_hash(
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    raw_refresh = login("acme", "rahul@acme.com").json()["refresh_token"]

    stored = db_session.scalars(select(RefreshToken)).all()
    assert len(stored) == 1
    assert stored[0].token_hash != raw_refresh
    assert raw_refresh not in stored[0].token_hash
    assert stored[0].tenant_id == tenant.id


# ---------------------------------------------------------------------------
# 6-10. Failure paths all look identical
# ---------------------------------------------------------------------------


def test_invalid_password_fails(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = login("acme", "rahul@acme.com", "not-the-right-password")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_invalid_email_fails(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = login("acme", "nobody@acme.com")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_invalid_tenant_slug_fails(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = login("no-such-tenant", "rahul@acme.com")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_inactive_user_cannot_log_in(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com", status=UserStatus.INACTIVE)

    response = login("acme", "rahul@acme.com")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_user_without_a_password_cannot_log_in(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """password_hash is nullable; such a user must fail closed."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com", password=None)

    response = login("acme", "rahul@acme.com")

    assert response.status_code == 401
    assert response.json()["detail"] == GENERIC_ERROR


def test_login_does_not_reveal_which_factor_was_wrong(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """No user enumeration: every failure is byte-identical."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com", status=UserStatus.ACTIVE)
    tenant_factory(slug="other")

    responses = [
        login("acme", "rahul@acme.com", "wrong-password"),  # bad password
        login("acme", "ghost@acme.com"),  # unknown user
        login("no-such-tenant", "rahul@acme.com"),  # unknown tenant
        login("other", "rahul@acme.com"),  # right user, wrong tenant
    ]

    assert {r.status_code for r in responses} == {401}
    # Identical bodies, so nothing distinguishes the cases.
    assert len({r.text for r in responses}) == 1
    for response in responses:
        body = response.text.lower()
        for leak in ("tenant", "user", "password", "email", "inactive", "exist"):
            assert leak not in body.replace("invalid credentials", "")


def test_login_rejects_smuggled_fields(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Extra body fields are refused outright rather than silently ignored."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")

    response = client.post(
        LOGIN_URL,
        json={
            "tenant_slug": "acme",
            "email": "rahul@acme.com",
            "password": DEFAULT_PASSWORD,
            "role": "SUPER_ADMIN",
            "tenant_id": str(tenant.id),
        },
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 11-12. Tenant scoping of the lookup
# ---------------------------------------------------------------------------


def test_same_email_in_two_tenants_resolves_by_slug(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """The slug alone must decide which of two identical emails is used."""
    acme = tenant_factory(slug="acme")
    beta = tenant_factory(slug="beta")
    acme_user = user_factory(acme, email="shared@example.com", employee_code="A-1")
    beta_user = user_factory(beta, email="shared@example.com", employee_code="B-1")

    assert acme_user.id != beta_user.id

    acme_token = login("acme", "shared@example.com").json()["access_token"]
    beta_token = login("beta", "shared@example.com").json()["access_token"]

    from app.services.auth.jwt import decode_access_token

    acme_claims = decode_access_token(acme_token)
    beta_claims = decode_access_token(beta_token)

    assert acme_claims.user_id == acme_user.id
    assert acme_claims.tenant_id == acme.id
    assert beta_claims.user_id == beta_user.id
    assert beta_claims.tenant_id == beta.id


def test_credentials_are_not_valid_in_a_sibling_tenant(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """A correct email+password must not work against another tenant's slug."""
    acme = tenant_factory(slug="acme")
    tenant_factory(slug="beta")
    user_factory(acme, email="rahul@acme.com")

    assert login("acme", "rahul@acme.com").status_code == 200
    assert login("beta", "rahul@acme.com").status_code == 401
