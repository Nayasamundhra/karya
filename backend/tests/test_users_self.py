"""Self-service account management (spec checks 50-63).

``/users/me``, profile update and password change — available to every role.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, RefreshToken, User
from app.services.auth.password import verify_password
from app.services.users import service as users_service
from tests.conftest import DEFAULT_PASSWORD, Org, auth_header

ME_URL = "/api/v1/users/me"
PASSWORD_URL = "/api/v1/users/me/password"
NEW_PASSWORD = "an-entirely-different-passphrase"


@pytest.fixture
def roles(org_factory: Callable[..., Org]) -> Org:
    return org_factory()


def tokens(org: Org) -> dict[str, str]:
    return {
        "STAFF": org.staff_token,
        "MANAGER": org.manager_token,
        "TENANT_ADMIN": org.admin_token,
    }


# ---------------------------------------------------------------------------
# 58-59. Own profile
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["STAFF", "MANAGER", "TENANT_ADMIN"])
def test_every_role_can_read_its_own_profile(
    client: TestClient, roles: Org, role: str
) -> None:
    response = client.get(ME_URL, headers=auth_header(tokens(roles)[role]))

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == role
    assert body["tenant_id"] == str(roles.tenant.id)
    assert "password_hash" not in body
    assert "$argon2" not in response.text
    assert set(body) == {
        "id", "tenant_id", "employee_code", "name", "email", "role", "status"
    }


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get(ME_URL).status_code == 401
    assert client.patch(ME_URL, json={"name": "x"}).status_code == 401
    assert client.post(PASSWORD_URL, json={}).status_code == 401


@pytest.mark.parametrize("role", ["STAFF", "MANAGER", "TENANT_ADMIN"])
def test_every_role_can_update_its_own_name(
    client: TestClient, roles: Org, role: str
) -> None:
    response = client.patch(
        ME_URL, json={"name": f"Renamed {role}"}, headers=auth_header(tokens(roles)[role])
    )

    assert response.status_code == 200
    assert response.json()["name"] == f"Renamed {role}"


@pytest.mark.parametrize(
    "smuggled",
    [
        {"role": "TENANT_ADMIN"},
        {"status": "INACTIVE"},
        {"tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"password_hash": "$argon2id$fake"},
        {"email": "hijack@acme.com"},
        {"employee_code": "ADM-9"},
        {"id": "22222222-2222-2222-2222-222222222222"},
        {"created_at": "2020-01-01T00:00:00Z"},
        {"updated_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_self_update_refuses_privileged_and_identity_fields(
    client: TestClient, roles: Org, smuggled: dict
) -> None:
    """Not declared in the schema, so an attempt is a loud 422 - not a silent no-op."""
    response = client.patch(
        ME_URL,
        json={"name": "Legit", **smuggled},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 422, smuggled


def test_staff_cannot_escalate_themselves_by_any_route(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    """Neither the self endpoint nor the admin one is open to a STAFF caller."""
    assert client.patch(
        ME_URL, json={"role": "TENANT_ADMIN"}, headers=auth_header(roles.staff_token)
    ).status_code == 422
    assert client.patch(
        f"/api/v1/users/{roles.staff.id}/role",
        json={"role": "TENANT_ADMIN"},
        headers=auth_header(roles.staff_token),
    ).status_code == 403

    db_session.expire_all()
    assert db_session.get(User, roles.staff.id).role == "STAFF"


# ---------------------------------------------------------------------------
# 50-57, 63. Password change
# ---------------------------------------------------------------------------


def test_correct_current_password_allows_a_change(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    response = client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    db_session.expire_all()
    user = db_session.get(User, roles.staff.id)
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert not verify_password(DEFAULT_PASSWORD, user.password_hash)


def test_old_password_stops_working_and_the_new_one_works(
    client: TestClient, roles: Org
) -> None:
    client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    def login(password: str) -> int:
        return client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": "acme", "email": "staff@acme.com",
                  "password": password},
        ).status_code

    assert login(DEFAULT_PASSWORD) == 401
    assert login(NEW_PASSWORD) == 200


def test_wrong_current_password_is_a_generic_401(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    """And it reveals nothing about whether the new password would be acceptable."""
    response = client.post(
        PASSWORD_URL,
        json={"current_password": "not-the-right-one", "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
    db_session.expire_all()
    assert verify_password(
        DEFAULT_PASSWORD, db_session.get(User, roles.staff.id).password_hash
    )


def test_wrong_current_password_is_checked_before_the_new_one(
    client: TestClient, roles: Org
) -> None:
    """A caller who has not proven ownership gets no feedback on the new value."""
    same_as_current = client.post(
        PASSWORD_URL,
        json={"current_password": "wrong", "new_password": DEFAULT_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    # Would be 400 "must differ" if the new password were evaluated first.
    assert same_as_current.status_code == 401
    assert same_as_current.json()["detail"] == "Invalid credentials"


def test_new_password_must_differ_from_the_current_one(
    client: TestClient, roles: Org
) -> None:
    response = client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": DEFAULT_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 400
    assert "differ" in response.json()["detail"]


@pytest.mark.parametrize("weak", ["short", "1234567"])
def test_new_password_must_meet_the_length_policy(
    client: TestClient, roles: Org, weak: str
) -> None:
    response = client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": weak},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 422


def test_new_password_may_not_be_the_accounts_own_identifiers(
    client: TestClient, roles: Org
) -> None:
    response = client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": "staff@acme.com"},
        headers=auth_header(roles.staff_token),
    )

    assert response.status_code == 400
    assert "email" in response.json()["detail"]


def test_password_change_revokes_every_refresh_session(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    """A changed password usually means the old one is suspect."""
    active_before = db_session.scalar(
        select(func.count()).select_from(RefreshToken)
        .where(RefreshToken.user_id == roles.staff.id,
               RefreshToken.revoked_at.is_(None))
    )
    assert active_before == 1

    body = client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    ).json()

    assert body["sessions_revoked"] == 1
    db_session.expire_all()
    assert db_session.scalar(
        select(func.count()).select_from(RefreshToken)
        .where(RefreshToken.user_id == roles.staff.id,
               RefreshToken.revoked_at.is_(None))
    ) == 0


def test_password_change_is_audited_without_either_password(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    client.post(
        PASSWORD_URL,
        json={"current_password": DEFAULT_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    entry = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == users_service.ACTION_PASSWORD_CHANGED
        )
    ).one()
    assert entry.actor_user_id == roles.staff.id
    assert entry.target_id == roles.staff.id
    assert entry.tenant_id == roles.tenant.id
    rendered = str(entry.log_metadata)
    assert DEFAULT_PASSWORD not in rendered
    assert NEW_PASSWORD not in rendered
    assert "$argon2" not in rendered
    assert entry.log_metadata["sessions_revoked"] == 1


def test_failed_password_change_writes_no_audit_row(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    client.post(
        PASSWORD_URL,
        json={"current_password": "wrong", "new_password": NEW_PASSWORD},
        headers=auth_header(roles.staff_token),
    )

    assert db_session.scalar(
        select(func.count()).select_from(AuditLog)
        .where(AuditLog.action == users_service.ACTION_PASSWORD_CHANGED)
    ) == 0


def test_password_change_accepts_no_target_user(
    client: TestClient, db_session: Session, roles: Org
) -> None:
    """There is no field through which an admin could set someone else's password."""
    response = client.post(
        PASSWORD_URL,
        json={
            "current_password": DEFAULT_PASSWORD,
            "new_password": NEW_PASSWORD,
            "user_id": str(roles.staff.id),
        },
        headers=auth_header(roles.admin_token),
    )

    assert response.status_code == 422
    db_session.expire_all()
    assert verify_password(
        DEFAULT_PASSWORD, db_session.get(User, roles.staff.id).password_hash
    )
