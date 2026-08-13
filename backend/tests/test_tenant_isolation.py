"""Cross-tenant isolation (spec checks 35-39).

The scenario throughout is the one named in the specification:

    Tenant A - "Acme Technologies"  - Rahul
    Tenant B - "Beta Technologies"  - Priya

Rahul authenticates, then tries to reach Tenant B context through the body,
query string, headers and a forged token. Every attempt must fail or be ignored.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentTenantId, CurrentUser
from app.core.config import settings
from app.db.session import get_db
from app.db.tenant_scope import get_tenant_owned, tenant_scoped_select
from app.models import RefreshToken, Tenant, User
from tests.conftest import auth_header, make_get_db_override

ME_URL = "/api/v1/auth/me"


@pytest.fixture
def two_tenants(
    tenant_factory: Callable[..., Tenant], user_factory: Callable[..., User]
) -> tuple[Tenant, User, Tenant, User]:
    """Acme/Rahul and Beta/Priya."""
    acme = tenant_factory(slug="acme", name="Acme Technologies")
    beta = tenant_factory(slug="beta", name="Beta Technologies")
    rahul = user_factory(
        acme, email="rahul@acme.com", employee_code="A-1", name="Rahul"
    )
    priya = user_factory(
        beta, email="priya@beta.com", employee_code="B-1", name="Priya"
    )
    return acme, rahul, beta, priya


# ---------------------------------------------------------------------------
# 35. Tenant A user cannot reach Tenant B context
# ---------------------------------------------------------------------------


def test_authenticated_user_only_ever_sees_their_own_tenant(
    client: TestClient,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    acme, rahul, beta, priya = two_tenants
    token = login("acme", "rahul@acme.com").json()["access_token"]

    body = client.get(ME_URL, headers=auth_header(token)).json()

    assert body["tenant_id"] == str(acme.id)
    assert body["tenant_id"] != str(beta.id)
    assert body["id"] == str(rahul.id)
    # Nothing about Tenant B appears in the response.
    assert str(beta.id) not in client.get(ME_URL, headers=auth_header(token)).text
    assert str(priya.id) not in client.get(ME_URL, headers=auth_header(token)).text


def test_tenant_b_credentials_do_not_work_against_tenant_a(
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    assert login("acme", "priya@beta.com").status_code == 401
    assert login("beta", "rahul@acme.com").status_code == 401


# ---------------------------------------------------------------------------
# 36-38. Impersonation attempts via body, query and headers
# ---------------------------------------------------------------------------


def test_tenant_cannot_be_switched_via_request_body(
    client: TestClient,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    acme, _rahul, beta, _priya = two_tenants
    token = login("acme", "rahul@acme.com").json()["access_token"]

    response = client.request(
        "GET",
        ME_URL,
        json={"tenant_id": str(beta.id), "tenant_slug": "beta"},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(acme.id)


def test_tenant_cannot_be_switched_via_query_parameters(
    client: TestClient,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    acme, _rahul, beta, _priya = two_tenants
    token = login("acme", "rahul@acme.com").json()["access_token"]

    for params in (
        {"tenant_id": str(beta.id)},
        {"tenant_slug": "beta"},
        {"tenant_id": str(beta.id), "role": "SUPER_ADMIN"},
    ):
        response = client.get(ME_URL, params=params, headers=auth_header(token))
        assert response.status_code == 200
        assert response.json()["tenant_id"] == str(acme.id)


def test_tenant_cannot_be_switched_via_headers(
    client: TestClient,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    acme, _rahul, beta, _priya = two_tenants
    token = login("acme", "rahul@acme.com").json()["access_token"]

    for extra in (
        {"X-Tenant-Id": str(beta.id)},
        {"X-Tenant-Slug": "beta"},
        {"X-Role": "SUPER_ADMIN"},
    ):
        response = client.get(ME_URL, headers={**auth_header(token), **extra})
        assert response.status_code == 200
        assert response.json()["tenant_id"] == str(acme.id)


def test_token_with_a_mismatched_tenant_claim_is_rejected(
    client: TestClient,
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """A token naming another tenant for a real user must not be accepted.

    Signed with the real key, so this models a stale claim or a leaked secret;
    the consistency check against the database catches it either way.
    """
    _acme, rahul, beta, _priya = two_tenants
    forged = jwt.encode(
        {
            "sub": str(rahul.id),
            "tenant_id": str(beta.id),  # Rahul does not belong to Beta
            "role": "TENANT_ADMIN",
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    assert client.get(ME_URL, headers=auth_header(forged)).status_code == 401


# ---------------------------------------------------------------------------
# 39. Tenant membership comes from the database
# ---------------------------------------------------------------------------


def test_tenant_context_dependency_derives_from_the_database(
    db_session: Session,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """`CurrentTenantId` must equal the user's stored tenant, whatever is sent."""
    acme, rahul, beta, _priya = two_tenants

    probe = FastAPI()

    @probe.get("/tenant-context")
    def tenant_context(
        tenant_id: CurrentTenantId, current_user: CurrentUser
    ) -> dict[str, str]:
        return {
            "tenant_id": str(tenant_id),
            "user_tenant_id": str(current_user.tenant_id),
        }

    probe.dependency_overrides[get_db] = make_get_db_override(db_session)

    with TestClient(probe) as probe_client:
        # Log in through the real app to obtain a genuine token.
        token = login("acme", "rahul@acme.com").json()["access_token"]
        response = probe_client.get(
            "/tenant-context",
            params={"tenant_id": str(beta.id)},
            headers={**auth_header(token), "X-Tenant-Id": str(beta.id)},
        )

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(acme.id),
        "user_tenant_id": str(acme.id),
    }
    assert rahul.tenant_id == acme.id


def test_tenant_scoped_select_excludes_other_tenants(
    db_session: Session,
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """The reusable query helper must never return another tenant's rows."""
    acme, rahul, beta, priya = two_tenants

    acme_users = db_session.scalars(tenant_scoped_select(User, acme.id)).all()
    beta_users = db_session.scalars(tenant_scoped_select(User, beta.id)).all()

    assert [u.id for u in acme_users] == [rahul.id]
    assert [u.id for u in beta_users] == [priya.id]


def test_get_tenant_owned_hides_cross_tenant_rows(
    db_session: Session,
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """Fetching another tenant's row by id must look exactly like 'not found'."""
    acme, rahul, _beta, priya = two_tenants

    assert (
        get_tenant_owned(db_session, User, entity_id=rahul.id, tenant_id=acme.id)
        is not None
    )
    # Priya's real id, requested in Acme's context -> None, not Priya.
    assert (
        get_tenant_owned(db_session, User, entity_id=priya.id, tenant_id=acme.id)
        is None
    )


def test_refresh_tokens_are_tenant_scoped(
    db_session: Session,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """A session row must carry the owner's tenant, isolating it like any other."""
    acme, rahul, beta, _priya = two_tenants

    login("acme", "rahul@acme.com")
    login("beta", "priya@beta.com")

    acme_tokens = db_session.scalars(
        tenant_scoped_select(RefreshToken, acme.id)
    ).all()
    beta_tokens = db_session.scalars(select(RefreshToken)).all()

    assert len(acme_tokens) == 1
    assert acme_tokens[0].user_id == rahul.id
    assert acme_tokens[0].tenant_id == acme.id
    # Two sessions exist overall, but Acme's scope sees only its own.
    assert len(beta_tokens) == 2


def test_one_tenants_refresh_token_cannot_be_reassigned(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    two_tenants: tuple[Tenant, User, Tenant, User],
) -> None:
    """Tampering with a session's tenant must invalidate it, not move it."""
    _acme, _rahul, beta, _priya = two_tenants
    raw = login("acme", "rahul@acme.com").json()["refresh_token"]

    record = db_session.scalars(select(RefreshToken)).one()
    record.tenant_id = beta.id  # simulate corrupted/tampered state
    db_session.flush()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})

    assert response.status_code == 401
