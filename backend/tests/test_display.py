"""Office-display (kiosk) tokens: management endpoints, and the separate,
non-user authentication path they grant for minting a QR challenge.

A display token is deliberately not a user session - `test_display_token_
is_not_accepted_as_a_user_bearer_token` and
`test_user_bearer_token_is_not_accepted_as_a_display_token` are the two
tests that would catch the dependencies ever being merged by accident.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AttendanceLocation, Tenant, User, UserRole
from app.models.audit_log import AuditLog
from app.models.display_token import DisplayToken
from app.services.presence.display import (
    ACTION_DISPLAY_TOKEN_CREATED,
    ACTION_DISPLAY_TOKEN_REVOKED,
)
from tests.conftest import auth_header

CREATE_PATH = "/api/v1/tenant/display-tokens"
DISPLAY_QR_PATH = "/api/v1/presence/qr/challenge/display"


@pytest.fixture
def tenant_with_location(
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
) -> Tenant:
    tenant = tenant_factory(slug="display-co")
    location_factory(tenant)
    return tenant


@pytest.fixture
def admin_token(
    tenant_with_location: Tenant,
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> str:
    user_factory(
        tenant_with_location,
        email="admin@display-co.com",
        role=UserRole.TENANT_ADMIN,
    )
    return login("display-co", "admin@display-co.com").json()["access_token"]


def test_tenant_admin_can_create_a_display_token(
    client: TestClient, admin_token: str, db_session: Session, tenant_with_location: Tenant
) -> None:
    response = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["label"] == "Reception tablet"
    assert body["token"]  # the raw secret, returned exactly once

    record = db_session.scalar(
        select(DisplayToken).where(DisplayToken.tenant_id == tenant_with_location.id)
    )
    assert record is not None
    assert record.label == "Reception tablet"
    # The raw token is never what's persisted.
    assert record.token_hash != body["token"]


def test_creating_a_display_token_writes_an_audit_row(
    client: TestClient, admin_token: str, db_session: Session, tenant_with_location: Tenant
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    token_id = create.json()["id"]

    entry = db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_with_location.id,
            AuditLog.action == ACTION_DISPLAY_TOKEN_CREATED,
        )
    )
    assert entry is not None
    assert entry.target_id == uuid.UUID(token_id)
    assert entry.log_metadata == {"label": "Reception tablet"}
    # The raw token must never end up in an audit row.
    assert create.json()["token"] not in str(entry.log_metadata)


def test_staff_cannot_create_a_display_token(
    client: TestClient,
    tenant_with_location: Tenant,
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    user_factory(tenant_with_location, email="staff@display-co.com", role=UserRole.STAFF)
    token = login("display-co", "staff@display-co.com").json()["access_token"]

    response = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(token)
    )
    assert response.status_code == 403


def test_manager_can_create_list_and_revoke_a_display_token(
    client: TestClient,
    tenant_with_location: Tenant,
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    """`QR_ISSUER_ROLES` includes MANAGER alongside TENANT_ADMIN - every other
    test in this module only exercises the admin path, so this is the one
    proof a manager's token actually works the same way, not just that the
    role constant lists it."""
    user_factory(tenant_with_location, email="manager@display-co.com", role=UserRole.MANAGER)
    token = login("display-co", "manager@display-co.com").json()["access_token"]

    create = client.post(
        CREATE_PATH, json={"label": "Warehouse tablet"}, headers=auth_header(token)
    )
    assert create.status_code == 201
    token_id = create.json()["id"]

    listing = client.get(CREATE_PATH, headers=auth_header(token))
    assert listing.status_code == 200
    assert any(item["id"] == token_id for item in listing.json()["items"])

    revoke = client.post(f"{CREATE_PATH}/{token_id}/revoke", headers=auth_header(token))
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None


def test_creating_a_display_token_requires_an_attendance_location(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    # No location_factory call here - this tenant has none yet.
    tenant = tenant_factory(slug="no-location-co")
    user_factory(tenant, email="admin@no-location-co.com", role=UserRole.TENANT_ADMIN)
    token = login("no-location-co", "admin@no-location-co.com").json()["access_token"]

    response = client.post(
        CREATE_PATH, json={"label": "Lobby screen"}, headers=auth_header(token)
    )
    assert response.status_code == 409


def test_listing_never_includes_the_raw_token(
    client: TestClient, admin_token: str
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    raw_token = create.json()["token"]

    listing = client.get(CREATE_PATH, headers=auth_header(admin_token))
    assert listing.status_code == 200
    body_text = listing.text
    assert raw_token not in body_text
    assert listing.json()["items"][0]["label"] == "Reception tablet"


def test_revoking_a_display_token_disables_it(
    client: TestClient, admin_token: str
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    token_id = create.json()["id"]
    raw_token = create.json()["token"]

    revoke = client.post(
        f"{CREATE_PATH}/{token_id}/revoke", headers=auth_header(admin_token)
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None

    mint = client.post(DISPLAY_QR_PATH, headers=auth_header(raw_token))
    assert mint.status_code == 401


def test_revoking_a_display_token_writes_an_audit_row_exactly_once(
    client: TestClient, admin_token: str, db_session: Session, tenant_with_location: Tenant
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    token_id = create.json()["id"]

    client.post(f"{CREATE_PATH}/{token_id}/revoke", headers=auth_header(admin_token))
    # Revoking an already-revoked token is a no-op, not a second event.
    client.post(f"{CREATE_PATH}/{token_id}/revoke", headers=auth_header(admin_token))

    entries = db_session.scalars(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_with_location.id,
            AuditLog.action == ACTION_DISPLAY_TOKEN_REVOKED,
        )
    ).all()
    assert len(entries) == 1
    assert entries[0].target_id == uuid.UUID(token_id)


def test_revoking_another_tenants_display_token_is_404(
    client: TestClient,
    admin_token: str,
    tenant_factory: Callable[..., Tenant],
    location_factory: Callable[..., AttendanceLocation],
    user_factory: Callable[..., User],
    login: Callable[..., object],
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    token_id = create.json()["id"]

    other_tenant = tenant_factory(slug="other-display-co")
    location_factory(other_tenant)
    user_factory(other_tenant, email="admin@other-display-co.com", role=UserRole.TENANT_ADMIN)
    other_admin_token = login(
        "other-display-co", "admin@other-display-co.com"
    ).json()["access_token"]

    response = client.post(
        f"{CREATE_PATH}/{token_id}/revoke", headers=auth_header(other_admin_token)
    )
    assert response.status_code == 404


def test_a_display_token_mints_a_qr_challenge(
    client: TestClient, admin_token: str
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    raw_token = create.json()["token"]

    response = client.post(DISPLAY_QR_PATH, headers=auth_header(raw_token))

    assert response.status_code == 201
    body = response.json()
    assert body["challenge_id"]
    assert body["nonce"]
    assert body["expires_in"] == settings.qr_challenge_ttl_seconds


def test_a_display_can_revoke_itself(
    client: TestClient, admin_token: str, db_session: Session, tenant_with_location: Tenant
) -> None:
    """The kiosk-side "Reset this display" control: a display token
    disabling its own credential, with no admin bearer token involved."""
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    token_id = create.json()["id"]
    raw_token = create.json()["token"]

    response = client.post("/api/v1/display/revoke-self", headers=auth_header(raw_token))
    assert response.status_code == 200
    assert response.json()["revoked_at"] is not None

    # The now-revoked token can no longer authenticate anything, including
    # another self-revoke attempt.
    again = client.post("/api/v1/display/revoke-self", headers=auth_header(raw_token))
    assert again.status_code == 401

    entry = db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_with_location.id,
            AuditLog.action == ACTION_DISPLAY_TOKEN_REVOKED,
            AuditLog.target_id == uuid.UUID(token_id),
        )
    )
    assert entry is not None
    # A self-revoke has no human actor.
    assert entry.actor_user_id is None


def test_revoking_self_does_not_require_or_accept_a_user_bearer_token(
    client: TestClient, admin_token: str
) -> None:
    response = client.post("/api/v1/display/revoke-self", headers=auth_header(admin_token))
    assert response.status_code == 401


def test_display_qr_endpoint_rejects_a_missing_or_unknown_token(
    client: TestClient,
) -> None:
    assert client.post(DISPLAY_QR_PATH).status_code == 401
    assert (
        client.post(DISPLAY_QR_PATH, headers=auth_header("not-a-real-token")).status_code
        == 401
    )


def test_display_token_is_not_accepted_as_a_user_bearer_token(
    client: TestClient, admin_token: str
) -> None:
    """A display token must never work against an ordinary user-authenticated
    route - it identifies a kiosk, not a person, and grants exactly one
    capability."""
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    raw_token = create.json()["token"]

    response = client.get("/api/v1/auth/me", headers=auth_header(raw_token))
    assert response.status_code == 401


def test_user_bearer_token_is_not_accepted_as_a_display_token(
    client: TestClient, admin_token: str
) -> None:
    """The inverse of the above: a real user's access token must not work
    against the display-only endpoint either."""
    response = client.post(DISPLAY_QR_PATH, headers=auth_header(admin_token))
    assert response.status_code == 401


def test_using_a_display_token_bumps_its_heartbeat(
    client: TestClient, admin_token: str, db_session: Session
) -> None:
    create = client.post(
        CREATE_PATH, json={"label": "Reception tablet"}, headers=auth_header(admin_token)
    )
    raw_token = create.json()["token"]
    token_id = create.json()["id"]

    record = db_session.get(DisplayToken, token_id)
    assert record.last_used_at is None

    client.post(DISPLAY_QR_PATH, headers=auth_header(raw_token))

    db_session.refresh(record)
    assert record.last_used_at is not None
