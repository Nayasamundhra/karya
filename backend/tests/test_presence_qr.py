"""Static QR-token resolution (`app.services.presence.qr`) and regeneration."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.models import AttendanceLocation, Tenant, User, UserRole
from app.services.presence import qr as qr_service
from tests.conftest import auth_header

REGENERATE_URL = "/api/v1/tenant/me/location/qr-token/regenerate"


def test_token_resolves_to_its_own_active_location(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant)

    resolved = qr_service.resolve_location_by_qr_token(
        db_session, qr_token=location.qr_token
    )

    assert resolved is not None
    assert resolved.id == location.id


def test_unknown_token_resolves_to_nothing(db_session: Session) -> None:
    assert (
        qr_service.resolve_location_by_qr_token(db_session, qr_token=uuid.uuid4())
        is None
    )


def test_inactive_locations_token_does_not_resolve(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant, status="INACTIVE")

    assert (
        qr_service.resolve_location_by_qr_token(db_session, qr_token=location.qr_token)
        is None
    )


def test_each_location_gets_its_own_unique_token(
    db_session: Session,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    acme = location_factory(tenant_factory(slug="acme"))
    beta = location_factory(tenant_factory(slug="beta"))

    assert acme.qr_token != beta.qr_token


# ---------------------------------------------------------------------------
# Regeneration - the compensating control for a leaked/over-shared code
# ---------------------------------------------------------------------------


def test_tenant_admin_can_regenerate_the_qr_token(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant)
    old_token = location.qr_token
    user_factory(tenant, email="admin@acme.com", role=UserRole.TENANT_ADMIN)
    token = login("acme", "admin@acme.com").json()["access_token"]

    response = client.post(REGENERATE_URL, headers=auth_header(token))

    assert response.status_code == 200
    new_token = uuid.UUID(response.json()["qr_token"])
    assert new_token != old_token

    # The old token no longer resolves; the new one does.
    assert (
        qr_service.resolve_location_by_qr_token(db_session, qr_token=old_token) is None
    )
    resolved = qr_service.resolve_location_by_qr_token(db_session, qr_token=new_token)
    assert resolved is not None
    assert resolved.id == location.id


@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.STAFF])
def test_only_tenant_admin_can_regenerate(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
    role: UserRole,
) -> None:
    tenant = tenant_factory(slug="acme")
    location_factory(tenant)
    user_factory(tenant, email="u@acme.com", role=role)
    token = login("acme", "u@acme.com").json()["access_token"]

    assert client.post(REGENERATE_URL, headers=auth_header(token)).status_code == 403


def test_regenerate_requires_an_existing_location(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="admin@acme.com", role=UserRole.TENANT_ADMIN)
    token = login("acme", "admin@acme.com").json()["access_token"]

    response = client.post(REGENERATE_URL, headers=auth_header(token))

    assert response.status_code == 404


def test_regenerate_is_tenant_scoped(
    client: TestClient,
    db_session: Session,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., AttendanceLocation],
) -> None:
    acme = tenant_factory(slug="acme")
    beta = tenant_factory(slug="beta")
    beta_location = location_factory(beta)
    beta_token = beta_location.qr_token
    user_factory(acme, email="admin@acme.com", role=UserRole.TENANT_ADMIN)
    token = login("acme", "admin@acme.com").json()["access_token"]

    client.post(REGENERATE_URL, headers=auth_header(token))

    # Beta's own token is untouched by Acme's admin action.
    db_session.refresh(beta_location)
    assert beta_location.qr_token == beta_token
