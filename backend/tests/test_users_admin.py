"""Tenant-admin user management (spec checks 1-27, 28-38, 42-44).

Creation, listing, detail, profile update, role change, lifecycle and the one
irreversible operation, deletion.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceEventType,
    AuditLog,
    RefreshToken,
    User,
    UserRole,
    UserStatus,
)
from app.services.auth.password import verify_password
from app.services.users import service as users_service
from tests.conftest import Org, auth_header

USERS_URL = "/api/v1/users"
NEW_PASSWORD = "a-brand-new-staff-password"


def admin(org: Org) -> dict[str, str]:
    return auth_header(org.admin_token)


def create_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": "newhire@acme.com",
        "password": NEW_PASSWORD,
        "name": "New Hire",
        "employee_code": "EMP-100",
    }
    payload.update(overrides)
    return payload


def audit_actions(session: Session) -> list[str]:
    return [a for (a,) in session.execute(select(AuditLog.action))]


# ---------------------------------------------------------------------------
# 1-13. Creation
# ---------------------------------------------------------------------------


def test_admin_can_create_staff(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.post(USERS_URL, json=create_payload(), headers=admin(o))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newhire@acme.com"
    assert body["role"] == "STAFF"
    assert body["status"] == "ACTIVE"
    assert body["tenant_id"] == str(o.tenant.id)
    assert "password" not in body
    assert "password_hash" not in body

    created = db_session.scalar(select(User).where(User.id == uuid.UUID(body["id"])))
    assert created is not None
    assert created.tenant_id == o.tenant.id


@pytest.mark.parametrize("role", ["STAFF", "MANAGER", "TENANT_ADMIN"])
def test_admin_can_create_each_tenant_role(
    client: TestClient, org_factory: Callable[..., Org], role: str
) -> None:
    o = org_factory()

    # Emails must not collide with the fixture's own admin/manager/staff users.
    response = client.post(
        USERS_URL,
        json=create_payload(
            role=role,
            email=f"new-{role.lower()}@acme.com",
            employee_code=f"NEW-{role[:3]}",
        ),
        headers=admin(o),
    )

    assert response.status_code == 201
    assert response.json()["role"] == role


def test_super_admin_cannot_be_created_within_a_tenant(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """Tenant administration must not be a route to platform access."""
    o = org_factory()

    response = client.post(
        USERS_URL, json=create_payload(role="SUPER_ADMIN"), headers=admin(o)
    )

    assert response.status_code == 422


def test_password_is_stored_as_an_argon2id_hash(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    body = client.post(USERS_URL, json=create_payload(), headers=admin(o)).json()

    created = db_session.scalar(select(User).where(User.id == uuid.UUID(body["id"])))
    assert created is not None
    assert created.password_hash is not None
    assert created.password_hash.startswith("$argon2id$")
    assert NEW_PASSWORD not in created.password_hash
    assert verify_password(NEW_PASSWORD, created.password_hash)


def test_created_user_can_log_in(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.post(USERS_URL, json=create_payload(), headers=admin(o))

    login = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme",
            "email": "newhire@acme.com",
            "password": NEW_PASSWORD,
        },
    )

    assert login.status_code == 200
    assert login.json()["access_token"]


def test_creation_writes_an_audit_row_without_the_password(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    body = client.post(USERS_URL, json=create_payload(), headers=admin(o)).json()

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == users_service.ACTION_USER_CREATED)
    ).one()
    assert entry.tenant_id == o.tenant.id
    assert entry.actor_user_id == o.admin.id
    assert entry.target_type == "User"
    assert str(entry.target_id) == body["id"]
    assert entry.log_metadata is not None
    assert entry.log_metadata["role"] == "STAFF"
    rendered = str(entry.log_metadata)
    assert NEW_PASSWORD not in rendered
    assert "password" not in rendered.lower()
    assert "$argon2" not in rendered


def test_duplicate_email_in_the_same_tenant_is_a_clean_409(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    """A constraint violation must never surface as a database error."""
    o = org_factory()
    assert client.post(USERS_URL, json=create_payload(), headers=admin(o)).status_code == 201

    response = client.post(
        USERS_URL, json=create_payload(employee_code="EMP-101"), headers=admin(o)
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "email" in detail.lower()
    for leaked in ("IntegrityError", "psycopg", "uq_users", "SELECT", "INSERT"):
        assert leaked not in response.text


def test_duplicate_employee_code_is_a_clean_409(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.post(USERS_URL, json=create_payload(), headers=admin(o))

    response = client.post(
        USERS_URL, json=create_payload(email="other@acme.com"), headers=admin(o)
    )

    assert response.status_code == 409
    assert "employee code" in response.json()["detail"].lower()


def test_failed_creation_writes_no_audit_row_and_no_user(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    """The mutation and its audit row commit together, or neither does."""
    o = org_factory()
    client.post(USERS_URL, json=create_payload(), headers=admin(o))
    users_before = db_session.scalar(select(func.count()).select_from(User))
    audits_before = db_session.scalar(select(func.count()).select_from(AuditLog))

    assert client.post(
        USERS_URL, json=create_payload(employee_code="EMP-101"), headers=admin(o)
    ).status_code == 409

    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(User)) == users_before
    assert db_session.scalar(select(func.count()).select_from(AuditLog)) == audits_before


def test_same_email_may_exist_in_another_tenant(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")

    first = client.post(
        USERS_URL, json=create_payload(email="shared@example.com"), headers=admin(acme)
    )
    second = client.post(
        USERS_URL, json=create_payload(email="shared@example.com"), headers=admin(beta)
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["tenant_id"] != second.json()["tenant_id"]


def test_email_is_normalised_to_lower_case(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """Casing must not be able to create a second account for one person."""
    o = org_factory()

    created = client.post(
        USERS_URL, json=create_payload(email="  NewHire@ACME.com  "), headers=admin(o)
    )
    assert created.status_code == 201
    assert created.json()["email"] == "newhire@acme.com"

    # A differently-cased duplicate is now a conflict, not a second user.
    again = client.post(
        USERS_URL,
        json=create_payload(email="NEWHIRE@acme.com", employee_code="EMP-101"),
        headers=admin(o),
    )
    assert again.status_code == 409

    # And login works whatever casing is typed.
    login = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "acme", "email": "NewHire@Acme.COM",
              "password": NEW_PASSWORD},
    )
    assert login.status_code == 200


@pytest.mark.parametrize("password", ["short", "1234567", ""])
def test_weak_passwords_are_rejected(
    client: TestClient, org_factory: Callable[..., Org], password: str
) -> None:
    o = org_factory()

    response = client.post(
        USERS_URL, json=create_payload(password=password), headers=admin(o)
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 14-21. Listing
# ---------------------------------------------------------------------------


def test_admin_lists_only_their_own_tenant(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    acme = org_factory(slug="acme")
    beta = org_factory(slug="beta")

    body = client.get(USERS_URL, headers=admin(acme)).json()

    ids = {item["id"] for item in body["items"]}
    assert ids == {str(acme.admin.id), str(acme.manager.id), str(acme.staff.id)}
    assert str(beta.staff.id) not in ids
    assert "beta" not in client.get(USERS_URL, headers=admin(acme)).text
    assert body["pagination"]["total"] == 3


def test_list_search_matches_name_email_and_code(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    for term, expected in (
        ("rahul", {str(o.staff.id)}),
        ("EMP-1", {str(o.staff.id)}),
        ("manager@acme.com", {str(o.manager.id)}),
        ("menon", {str(o.manager.id)}),
    ):
        body = client.get(USERS_URL, params={"search": term}, headers=admin(o)).json()
        assert {i["id"] for i in body["items"]} == expected, term


@pytest.mark.parametrize("term", ["%", "_", "%%", "a%b", "\\"])
def test_list_search_treats_like_wildcards_literally(
    client: TestClient, org_factory: Callable[..., Org], term: str
) -> None:
    """A `%` or `_` in the search term must match itself, not act as a wildcard.

    Unescaped, `%` becomes the pattern `%%%` and returns the entire tenant, and
    `_` matches any single character - so a search box would quietly leak the
    whole user list.
    """
    o = org_factory()

    body = client.get(USERS_URL, params={"search": term}, headers=admin(o)).json()

    assert body["items"] == [], term
    assert body["pagination"]["total"] == 0, term


def test_list_search_can_still_find_a_literal_underscore(
    client: TestClient, org_factory: Callable[..., Org],
    user_factory: Callable[..., User]
) -> None:
    """Escaping must not break searching for a name that contains one."""
    o = org_factory()
    user_factory(o.tenant, email="odd@acme.com", employee_code="X_1", name="Odd One")

    matched = client.get(USERS_URL, params={"search": "X_1"}, headers=admin(o)).json()
    assert {i["employee_code"] for i in matched["items"]} == {"X_1"}

    # "X_1" as a pattern would also match "XA1"; escaped, it does not.
    unmatched = client.get(
        USERS_URL, params={"search": "X.1"}, headers=admin(o)
    ).json()
    assert unmatched["items"] == []


@pytest.mark.parametrize(
    ("filters", "expected_key"),
    [({"role": "STAFF"}, "staff"), ({"role": "MANAGER"}, "manager"),
     ({"role": "TENANT_ADMIN"}, "admin")],
)
def test_list_filters_by_role(
    client: TestClient, org_factory: Callable[..., Org],
    filters: dict, expected_key: str
) -> None:
    o = org_factory()

    body = client.get(USERS_URL, params=filters, headers=admin(o)).json()

    assert {i["id"] for i in body["items"]} == {str(getattr(o, expected_key).id)}


def test_list_filters_by_status(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    o.staff.status = UserStatus.INACTIVE.value
    db_session.flush()

    active = client.get(USERS_URL, params={"status": "ACTIVE"}, headers=admin(o)).json()
    inactive = client.get(
        USERS_URL, params={"status": "INACTIVE"}, headers=admin(o)
    ).json()

    assert str(o.staff.id) not in {i["id"] for i in active["items"]}
    assert {i["id"] for i in inactive["items"]} == {str(o.staff.id)}


def test_list_pagination_is_bounded_and_stable(
    client: TestClient, org_factory: Callable[..., Org],
    user_factory: Callable[..., User]
) -> None:
    o = org_factory()
    for index in range(7):
        user_factory(
            o.tenant, email=f"extra{index}@acme.com",
            employee_code=f"X-{index}", name=f"Extra {index}",
        )

    seen: list[str] = []
    for page in (1, 2, 3, 4):
        body = client.get(
            USERS_URL, params={"page": page, "page_size": 3}, headers=admin(o)
        ).json()
        assert body["pagination"]["total"] == 10
        assert body["pagination"]["total_pages"] == 4
        seen.extend(i["id"] for i in body["items"])

    assert len(seen) == 10
    assert len(set(seen)) == 10  # no duplicates across pages

    assert client.get(
        USERS_URL, params={"page_size": 101}, headers=admin(o)
    ).status_code == 422
    assert client.get(
        USERS_URL, params={"page": 0}, headers=admin(o)
    ).status_code == 422


def test_list_requires_authentication(client: TestClient) -> None:
    assert client.get(USERS_URL).status_code == 401


# ---------------------------------------------------------------------------
# 10, 22-27. Detail and profile update
# ---------------------------------------------------------------------------


def test_admin_can_read_and_update_a_user(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    detail = client.get(f"{USERS_URL}/{o.staff.id}", headers=admin(o)).json()
    assert detail["id"] == str(o.staff.id)
    assert "created_at" in detail and "updated_at" in detail
    assert "password_hash" not in detail

    updated = client.patch(
        f"{USERS_URL}/{o.staff.id}",
        json={"name": "Rahul S. Sharma", "employee_code": "EMP-9"},
        headers=admin(o),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Rahul S. Sharma"
    assert updated.json()["employee_code"] == "EMP-9"


def test_patch_leaves_unsent_fields_alone(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """PATCH semantics, not PUT: absent fields keep their values."""
    o = org_factory()
    before = client.get(f"{USERS_URL}/{o.staff.id}", headers=admin(o)).json()

    after = client.patch(
        f"{USERS_URL}/{o.staff.id}", json={"name": "Only Name Changed"},
        headers=admin(o),
    ).json()

    assert after["name"] == "Only Name Changed"
    assert after["email"] == before["email"]
    assert after["employee_code"] == before["employee_code"]
    assert after["role"] == before["role"]
    assert after["status"] == before["status"]


def test_profile_update_writes_an_audit_row_with_before_and_after(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    client.patch(
        f"{USERS_URL}/{o.staff.id}", json={"name": "Renamed"}, headers=admin(o)
    )

    entry = db_session.scalars(
        select(AuditLog).where(AuditLog.action == users_service.ACTION_USER_UPDATED)
    ).one()
    assert entry.actor_user_id == o.admin.id
    assert entry.log_metadata is not None
    assert entry.log_metadata["changes"]["name"] == {
        "from": "Rahul Sharma", "to": "Renamed"
    }


def test_a_no_op_update_writes_no_audit_row(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.staff.id}", json={"name": "Rahul Sharma"}, headers=admin(o)
    )

    assert response.status_code == 200
    assert users_service.ACTION_USER_UPDATED not in audit_actions(db_session)


def test_update_to_a_taken_email_is_a_clean_409(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.staff.id}", json={"email": "manager@acme.com"},
        headers=admin(o),
    )

    assert response.status_code == 409
    assert "IntegrityError" not in response.text


# ---------------------------------------------------------------------------
# 28-35. Role changes
# ---------------------------------------------------------------------------


def test_admin_can_change_a_users_role(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.staff.id}/role", json={"role": "MANAGER"}, headers=admin(o)
    )

    assert response.status_code == 200
    assert response.json()["role"] == "MANAGER"

    entry = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == users_service.ACTION_USER_ROLE_CHANGED
        )
    ).one()
    assert entry.log_metadata == {
        "target_user_id": str(o.staff.id), "old_role": "STAFF", "new_role": "MANAGER"
    }


def test_admin_cannot_change_their_own_role(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """The most direct escalation path, closed for everyone including admins."""
    o = org_factory()

    response = client.patch(
        f"{USERS_URL}/{o.admin.id}/role", json={"role": "STAFF"}, headers=admin(o)
    )

    assert response.status_code == 403
    assert "your own role" in response.json()["detail"]


def test_role_change_rejects_unknown_and_platform_roles(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    for role in ("SUPER_ADMIN", "OWNER", "root", "", "staff"):
        response = client.patch(
            f"{USERS_URL}/{o.staff.id}/role", json={"role": role}, headers=admin(o)
        )
        assert response.status_code == 422, role


# ---------------------------------------------------------------------------
# 36-44. Lifecycle
# ---------------------------------------------------------------------------


def test_admin_can_deactivate_and_reactivate(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    deactivated = client.post(
        f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "INACTIVE"

    reactivated = client.post(f"{USERS_URL}/{o.staff.id}/activate", headers=admin(o))
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "ACTIVE"

    actions = audit_actions(db_session)
    assert users_service.ACTION_USER_DEACTIVATED in actions
    assert users_service.ACTION_USER_ACTIVATED in actions


def test_deactivation_revokes_refresh_sessions(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    """An unexpired refresh token must not outlive the access it represents."""
    o = org_factory()
    assert db_session.scalar(
        select(func.count()).select_from(RefreshToken)
        .where(RefreshToken.user_id == o.staff.id, RefreshToken.revoked_at.is_(None))
    ) == 1

    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))

    db_session.expire_all()
    assert db_session.scalar(
        select(func.count()).select_from(RefreshToken)
        .where(RefreshToken.user_id == o.staff.id, RefreshToken.revoked_at.is_(None))
    ) == 0


def test_deactivated_user_cannot_authenticate_or_act(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))

    # The still-unexpired access token stops working.
    assert client.get(
        "/api/v1/users/me", headers=auth_header(o.staff_token)
    ).status_code == 401
    # A fresh login is refused.
    assert client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "acme", "email": "staff@acme.com",
              "password": "correct-horse-battery-staple"},
    ).status_code == 401
    # And so is recording attendance.
    assert client.post(
        "/api/v1/attendance/check-in",
        json={"latitude": 12.9716, "longitude": 77.5946, "accuracy_meters": 10.0,
              "qr_token": str(uuid.uuid4())},
        headers=auth_header(o.staff_token),
    ).status_code == 401


def test_activation_does_not_reset_the_password(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """Silently clearing a credential would lock the person out, not help them."""
    o = org_factory()
    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))
    client.post(f"{USERS_URL}/{o.staff.id}/activate", headers=admin(o))

    login = client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "acme", "email": "staff@acme.com",
              "password": "correct-horse-battery-staple"},
    )

    assert login.status_code == 200


def test_admin_cannot_deactivate_themselves(
    client: TestClient, org_factory: Callable[..., Org],
    user_factory: Callable[..., User]
) -> None:
    o = org_factory()
    # A second admin exists, so the last-admin rule is not what refuses this.
    user_factory(o.tenant, email="admin2@acme.com", employee_code="ADM-2",
                 role=UserRole.TENANT_ADMIN)

    response = client.post(f"{USERS_URL}/{o.admin.id}/deactivate", headers=admin(o))

    assert response.status_code == 403
    assert "your own account" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Deletion - the one irreversible operation
# ---------------------------------------------------------------------------


def _add_events(
    user: User,
    factory: Callable[..., object],
    *,
    pairs: int = 2,
) -> None:
    """Give ``user`` ``pairs`` complete check-in / check-out days."""
    base = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    for day in range(pairs):
        start = base + timedelta(days=day)
        factory(user, event_type=AttendanceEventType.CHECK_IN, at=start)
        factory(
            user,
            event_type=AttendanceEventType.CHECK_OUT,
            at=start + timedelta(hours=8),
        )


def _event_count(session: Session, user_id: uuid.UUID) -> int:
    return session.scalar(
        select(func.count())
        .select_from(AttendanceEvent)
        .where(AttendanceEvent.user_id == user_id)
    ) or 0


def test_admin_can_permanently_delete_an_employee_and_their_history(
    client: TestClient,
    db_session: Session,
    org_factory: Callable[..., Org],
    attendance_event_factory: Callable[..., object],
) -> None:
    o = org_factory()
    _add_events(o.staff, attendance_event_factory, pairs=2)
    # A neighbour's history must be left completely alone.
    _add_events(o.manager, attendance_event_factory, pairs=1)
    assert _event_count(db_session, o.staff.id) == 4

    response = client.delete(f"{USERS_URL}/{o.staff.id}", headers=admin(o))

    assert response.status_code == 204
    assert response.content == b""
    db_session.expire_all()
    assert db_session.get(User, o.staff.id) is None
    assert _event_count(db_session, o.staff.id) == 0
    assert _event_count(db_session, o.manager.id) == 2
    # Authentication state goes with the person (ON DELETE CASCADE).
    assert db_session.scalar(
        select(func.count()).select_from(RefreshToken)
        .where(RefreshToken.user_id == o.staff.id)
    ) == 0


def test_admin_can_permanently_delete_a_manager(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()

    response = client.delete(f"{USERS_URL}/{o.manager.id}", headers=admin(o))

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(User, o.manager.id) is None


def test_deleting_leaves_an_audit_row_with_who_was_removed(
    client: TestClient,
    db_session: Session,
    org_factory: Callable[..., Org],
    attendance_event_factory: Callable[..., object],
) -> None:
    o = org_factory()
    _add_events(o.staff, attendance_event_factory, pairs=2)
    staff_id = o.staff.id

    client.delete(f"{USERS_URL}/{staff_id}", headers=admin(o))

    db_session.expire_all()
    row = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "USER_DELETED")
    )
    assert row is not None
    assert row.tenant_id == o.tenant.id
    assert row.actor_user_id == o.admin.id
    # `target_id` is an untyped UUID, so the row outlives the user it describes.
    assert row.target_type == "User"
    assert row.target_id == staff_id
    assert row.log_metadata == {
        "target_user_id": str(staff_id),
        "name": "Rahul Sharma",
        "email": "staff@acme.com",
        "employee_code": "EMP-1",
        "role": "STAFF",
        "attendance_events_deleted": 4,
    }
    # Nothing secret is ever written to the trail.
    assert "password" not in str(row.log_metadata).lower()


def test_earlier_audit_history_about_a_deleted_user_survives(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))
    client.post(f"{USERS_URL}/{o.staff.id}/activate", headers=admin(o))

    client.delete(f"{USERS_URL}/{o.staff.id}", headers=admin(o))

    db_session.expire_all()
    actions = {
        a for (a,) in db_session.execute(
            select(AuditLog.action).where(AuditLog.target_id == o.staff.id)
        )
    }
    assert {"USER_DEACTIVATED", "USER_ACTIVATED", "USER_DELETED"} <= actions


def test_deleted_user_can_no_longer_authenticate(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.delete(f"{USERS_URL}/{o.staff.id}", headers=admin(o))

    assert client.get(
        "/api/v1/users/me", headers=auth_header(o.staff_token)
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"tenant_slug": "acme", "email": "staff@acme.com",
              "password": "correct-horse-battery-staple"},
    ).status_code == 401


def test_a_deleted_users_email_and_code_can_be_reused(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """Unlike deactivation, deletion frees the identity for someone new."""
    o = org_factory()
    client.delete(f"{USERS_URL}/{o.staff.id}", headers=admin(o))

    response = client.post(
        USERS_URL,
        json=create_payload(email="staff@acme.com", employee_code="EMP-1"),
        headers=admin(o),
    )

    assert response.status_code == 201


def test_a_deleted_user_is_gone_from_lookups(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    client.delete(f"{USERS_URL}/{o.staff.id}", headers=admin(o))

    assert client.get(
        f"{USERS_URL}/{o.staff.id}", headers=admin(o)
    ).status_code == 404
    # A second delete is a plain 404, not an error and not a success.
    assert client.delete(
        f"{USERS_URL}/{o.staff.id}", headers=admin(o)
    ).status_code == 404


def test_admin_cannot_delete_themselves(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org],
    user_factory: Callable[..., User],
) -> None:
    o = org_factory()
    # A second admin exists, so this is the self-rule refusing, nothing else.
    user_factory(o.tenant, email="admin2@acme.com", employee_code="ADM-2",
                 role=UserRole.TENANT_ADMIN)

    response = client.delete(f"{USERS_URL}/{o.admin.id}", headers=admin(o))

    assert response.status_code == 403
    assert "your own account" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(User, o.admin.id) is not None


def test_an_administrator_cannot_be_deleted(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org],
    user_factory: Callable[..., User],
) -> None:
    o = org_factory()
    other_admin = user_factory(
        o.tenant, email="admin2@acme.com", employee_code="ADM-2",
        role=UserRole.TENANT_ADMIN,
    )

    response = client.delete(f"{USERS_URL}/{other_admin.id}", headers=admin(o))

    assert response.status_code == 403
    assert "Administrators cannot be deleted" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(User, other_admin.id) is not None
    assert "USER_DELETED" not in audit_actions(db_session)


def test_a_demoted_administrator_can_then_be_deleted(
    client: TestClient, org_factory: Callable[..., Org],
    user_factory: Callable[..., User],
) -> None:
    """The documented path for removing an admin: demote first, then delete."""
    o = org_factory()
    other_admin = user_factory(
        o.tenant, email="admin2@acme.com", employee_code="ADM-2",
        role=UserRole.TENANT_ADMIN,
    )
    client.patch(
        f"{USERS_URL}/{other_admin.id}/role",
        json={"role": "STAFF"}, headers=admin(o),
    )

    assert client.delete(
        f"{USERS_URL}/{other_admin.id}", headers=admin(o)
    ).status_code == 204


@pytest.mark.parametrize("who", ["manager_token", "staff_token"])
def test_only_a_tenant_admin_can_delete(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org],
    who: str,
) -> None:
    o = org_factory()
    token = getattr(o, who)

    response = client.delete(f"{USERS_URL}/{o.staff.id}", headers=auth_header(token))

    assert response.status_code == 403
    db_session.expire_all()
    assert db_session.get(User, o.staff.id) is not None


def test_delete_requires_authentication(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    o = org_factory()
    assert client.delete(f"{USERS_URL}/{o.staff.id}").status_code == 401


def test_delete_cannot_reach_another_tenant(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org],
    attendance_event_factory: Callable[..., object],
) -> None:
    """Cross-tenant ids are 404 - never 403 - and nothing of theirs is touched."""
    mine = org_factory("acme")
    theirs = org_factory("globex")
    _add_events(theirs.staff, attendance_event_factory, pairs=1)

    response = client.delete(f"{USERS_URL}/{theirs.staff.id}", headers=admin(mine))

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.get(User, theirs.staff.id) is not None
    assert _event_count(db_session, theirs.staff.id) == 2


def test_deactivation_is_still_non_destructive(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org],
    attendance_event_factory: Callable[..., object],
) -> None:
    """Deactivate keeps the person and their history; only DELETE erases them."""
    o = org_factory()
    _add_events(o.staff, attendance_event_factory, pairs=1)

    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))

    db_session.expire_all()
    assert db_session.get(User, o.staff.id) is not None
    assert _event_count(db_session, o.staff.id) == 2
