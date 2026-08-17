"""RBAC matrix, cross-tenant isolation and field smuggling (spec checks 39-42, 69-70, 73)."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AttendanceEvent, AuditLog, User, UserRole, UserStatus
from tests.conftest import Org, auth_header

USERS_URL = "/api/v1/users"


def paths_for(user_id: uuid.UUID) -> dict[str, tuple[str, str, dict | None]]:
    """Every administrative operation, keyed by a short label."""
    return {
        "list": ("GET", USERS_URL, None),
        "create": ("POST", USERS_URL, {
            "email": "x@acme.com", "password": "some-long-password",
            "name": "X", "employee_code": "X-1",
        }),
        "read": ("GET", f"{USERS_URL}/{user_id}", None),
        "update": ("PATCH", f"{USERS_URL}/{user_id}", {"name": "Changed"}),
        "role": ("PATCH", f"{USERS_URL}/{user_id}/role", {"role": "MANAGER"}),
        "activate": ("POST", f"{USERS_URL}/{user_id}/activate", None),
        "deactivate": ("POST", f"{USERS_URL}/{user_id}/deactivate", None),
        "audit": ("GET", f"{USERS_URL}/{user_id}/audit", None),
    }


# ---------------------------------------------------------------------------
# 40-41. The RBAC matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("caller", ["staff_token", "manager_token"])
def test_staff_and_manager_are_denied_every_admin_operation(
    client: TestClient, org_factory: Callable[..., Org], caller: str
) -> None:
    """Managers see attendance; identity and lifecycle belong to TENANT_ADMIN.

    Separation of duties: manager accounts are handed out far more freely, so a
    manager who could create logins or change roles would widen the blast radius
    of one compromised account to the whole tenant.
    """
    o = org_factory()
    headers = auth_header(getattr(o, caller))

    for label, (method, url, body) in paths_for(o.staff.id).items():
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code == 403, f"{caller} {label} -> {response.status_code}"
        assert response.json()["detail"] == "Insufficient permissions"


def test_tenant_admin_is_allowed_every_admin_operation(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    headers = auth_header(o.admin_token)

    for label, (method, url, body) in paths_for(o.staff.id).items():
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code < 400, f"{label} -> {response.status_code}"


@pytest.mark.parametrize("caller", ["staff_token", "manager_token", "admin_token"])
def test_every_role_gets_the_self_service_endpoints(
    client: TestClient, org_factory: Callable[..., Org], caller: str
) -> None:
    o = org_factory()
    headers = auth_header(getattr(o, caller))

    assert client.get(f"{USERS_URL}/me", headers=headers).status_code == 200
    assert client.patch(
        f"{USERS_URL}/me", json={"name": "Self Renamed"}, headers=headers
    ).status_code == 200
    assert client.get("/api/v1/tenant/me", headers=headers).status_code == 200


def test_only_tenant_admin_can_update_the_tenant(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    for token in (o.staff_token, o.manager_token):
        assert client.patch(
            "/api/v1/tenant/me", json={"name": "Renamed Co"},
            headers=auth_header(token),
        ).status_code == 403

    allowed = client.patch(
        "/api/v1/tenant/me", json={"name": "Renamed Co"},
        headers=auth_header(o.admin_token),
    )
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "Renamed Co"


@pytest.mark.parametrize("field", ["slug", "status", "id"])
def test_tenant_slug_status_and_id_are_not_writable(
    client: TestClient, org_factory: Callable[..., Org], field: str
) -> None:
    """The slug is what every employee types at login - renaming it locks them out."""
    o = org_factory()

    response = client.patch(
        "/api/v1/tenant/me",
        json={"name": "Fine", field: "hijacked"},
        headers=auth_header(o.admin_token),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 39, 69. Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_admin_cannot_touch_another_tenants_user(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    """Every operation must be a 404 - identical to an id that exists nowhere."""
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")
    headers = auth_header(acme.admin_token)

    operations = paths_for(beta.staff.id)
    del operations["list"]  # not addressed at a user
    del operations["create"]

    for label, (method, url, body) in operations.items():
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code == 404, f"{label} -> {response.status_code}"
        assert response.json() == {"detail": "User not found"}, label

    # Nothing about Beta's user changed.
    db_session.expire_all()
    target = db_session.get(User, beta.staff.id)
    assert target is not None
    assert target.role == UserRole.STAFF
    assert target.status == UserStatus.ACTIVE
    assert target.name == "Rahul Sharma"


def test_a_cross_tenant_id_is_indistinguishable_from_a_fictional_one(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")
    headers = auth_header(acme.admin_token)

    real_elsewhere = client.get(f"{USERS_URL}/{beta.staff.id}", headers=headers)
    pure_fiction = client.get(f"{USERS_URL}/{uuid.uuid4()}", headers=headers)

    assert real_elsewhere.status_code == pure_fiction.status_code == 404
    assert real_elsewhere.json() == pure_fiction.json()


def test_a_created_user_always_lands_in_the_callers_tenant(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")

    smuggled = client.post(
        USERS_URL,
        json={
            "email": "planted@acme.com", "password": "some-long-password",
            "name": "Planted", "employee_code": "P-1",
            "tenant_id": str(beta.tenant.id),
        },
        headers=auth_header(acme.admin_token),
    )
    assert smuggled.status_code == 422  # the field does not exist

    honest = client.post(
        USERS_URL,
        json={
            "email": "planted@acme.com", "password": "some-long-password",
            "name": "Planted", "employee_code": "P-1",
        },
        headers=auth_header(acme.admin_token),
    )
    assert honest.status_code == 201
    created = db_session.get(User, uuid.UUID(honest.json()["id"]))
    assert created is not None
    assert created.tenant_id == acme.tenant.id


def test_admin_list_and_audit_never_cross_tenants(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")
    # Generate an audit trail in Beta.
    client.patch(
        f"{USERS_URL}/{beta.staff.id}", json={"name": "Beta Renamed"},
        headers=auth_header(beta.admin_token),
    )

    listing = client.get(USERS_URL, headers=auth_header(acme.admin_token))
    assert str(beta.staff.id) not in listing.text
    assert "beta" not in listing.text.lower()

    # Acme's admin asking about their own user sees only their own audit rows.
    own_audit = client.get(
        f"{USERS_URL}/{acme.staff.id}/audit", headers=auth_header(acme.admin_token)
    ).json()
    assert own_audit["items"] == []


# ---------------------------------------------------------------------------
# 70. Field smuggling on the admin endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "smuggled",
    [
        {"tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"role": "TENANT_ADMIN"},
        {"status": "INACTIVE"},
        {"password_hash": "$argon2id$fake"},
        {"password": "sneaky-new-password"},
        {"id": "22222222-2222-2222-2222-222222222222"},
        {"created_at": "2020-01-01T00:00:00Z"},
        {"updated_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_generic_update_refuses_privileged_fields(
    client: TestClient, org_factory: Callable[..., Org], smuggled: dict
) -> None:
    """Role and status have dedicated endpoints; the rest are never writable."""
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.staff.id}",
        json={"name": "Legit", **smuggled},
        headers=auth_header(o.admin_token),
    )

    assert response.status_code == 422, smuggled


def test_role_endpoint_accepts_only_a_role(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.staff.id}/role",
        json={"role": "MANAGER", "status": "INACTIVE"},
        headers=auth_header(o.admin_token),
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 73. Attendance survives lifecycle changes
# ---------------------------------------------------------------------------


def test_attendance_history_survives_deactivation_and_reactivation(
    client: TestClient,
    db_session: Session,
    org_factory: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """Deactivation is a lifecycle change, never a purge."""
    from app.services.attendance import queries

    o = org_factory()
    today = queries.utc_today()
    attendance_day_factory(o.staff, today, (9, 17))
    before = db_session.scalar(select(func.count()).select_from(AttendanceEvent))
    assert before == 2

    def history_days() -> list[str]:
        body = client.get(
            f"/api/v1/attendance/users/{o.staff.id}/history",
            headers=auth_header(o.admin_token),
        ).json()
        return [i["status"] for i in body["items"] if i["status"] != "NO_RECORD"]

    assert history_days() == ["COMPLETED"]

    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=auth_header(o.admin_token))
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(AttendanceEvent)) == before
    assert history_days() == ["COMPLETED"]

    client.post(f"{USERS_URL}/{o.staff.id}/activate", headers=auth_header(o.admin_token))
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(AttendanceEvent)) == before
    assert history_days() == ["COMPLETED"]


def test_role_change_does_not_disturb_attendance(
    client: TestClient,
    db_session: Session,
    org_factory: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    from app.services.attendance import queries

    o = org_factory()
    attendance_day_factory(o.staff, queries.utc_today(), (9, 17))
    before = {e.id for e in db_session.scalars(select(AttendanceEvent))}

    client.patch(
        f"{USERS_URL}/{o.staff.id}/role", json={"role": "MANAGER"},
        headers=auth_header(o.admin_token),
    )

    db_session.expire_all()
    assert {e.id for e in db_session.scalars(select(AttendanceEvent))} == before


# ---------------------------------------------------------------------------
# 58-59. Audit endpoint privacy
# ---------------------------------------------------------------------------


def test_user_audit_returns_lifecycle_rows_only(
    client: TestClient,
    org_factory: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """Not a window onto the tenant's whole audit log."""
    from app.services.attendance import queries

    o = org_factory()
    attendance_day_factory(o.staff, queries.utc_today(), (9, 17))
    client.patch(
        f"{USERS_URL}/{o.staff.id}", json={"name": "Renamed"},
        headers=auth_header(o.admin_token),
    )
    client.patch(
        f"{USERS_URL}/{o.staff.id}/role", json={"role": "MANAGER"},
        headers=auth_header(o.admin_token),
    )

    body = client.get(
        f"{USERS_URL}/{o.staff.id}/audit", headers=auth_header(o.admin_token)
    ).json()

    actions = [i["action"] for i in body["items"]]
    assert set(actions) == {"USER_UPDATED", "USER_ROLE_CHANGED"}
    assert all(i["actor_user_id"] == str(o.admin.id) for i in body["items"])
    assert body["pagination"]["total"] == 2
    # No attendance, QR or presence rows leak in.
    for leaked in ("CHECK_IN", "PRESENCE", "QR_CHALLENGE", "nonce", "$argon2", "token"):
        assert leaked not in client.get(
            f"{USERS_URL}/{o.staff.id}/audit", headers=auth_header(o.admin_token)
        ).text
