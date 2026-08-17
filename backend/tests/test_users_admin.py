"""Tenant-admin user management (spec checks 1-27, 28-38, 42-44).

Creation, listing, detail, profile update, role change and lifecycle.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, RefreshToken, User, UserRole, UserStatus
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
              "challenge_id": str(uuid.uuid4()), "nonce": "x" * 20},
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


def test_no_user_is_ever_physically_deleted(
    client: TestClient, db_session: Session, org_factory: Callable[..., Org]
) -> None:
    """Karya is an audit system: identities persist so history stays resolvable."""
    o = org_factory()
    before = db_session.scalar(select(func.count()).select_from(User))

    client.post(f"{USERS_URL}/{o.staff.id}/deactivate", headers=admin(o))

    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(User)) == before
    assert db_session.get(User, o.staff.id) is not None
    # And there is no route that could delete one.
    assert client.request(
        "DELETE", f"{USERS_URL}/{o.staff.id}", headers=admin(o)
    ).status_code == 405
