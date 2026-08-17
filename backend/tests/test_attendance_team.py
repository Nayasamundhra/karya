"""Manager / tenant-admin attendance reads (spec checks 16-25, 43-46, 51).

Covers ``/attendance/team/today``, ``/attendance/users/{id}`` and their history
variants: RBAC, cross-tenant isolation, summary arithmetic and the N+1 guard.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceEventType,
    Tenant,
    User,
    UserRole,
    UserStatus,
)
from app.services.attendance import queries
from tests.conftest import auth_header

TEAM_URL = "/api/v1/attendance/team/today"
TODAY = queries.utc_today()
YESTERDAY = TODAY - timedelta(days=1)


def user_url(user_id: uuid.UUID | str) -> str:
    return f"/api/v1/attendance/users/{user_id}"


def user_history_url(user_id: uuid.UUID | str) -> str:
    return f"/api/v1/attendance/users/{user_id}/history"


@dataclass
class Org:
    tenant: Tenant
    staff: User
    manager: User
    admin: User
    staff_token: str
    manager_token: str
    admin_token: str


@pytest.fixture
def org(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> Callable[..., Org]:
    """A tenant with one STAFF, one MANAGER and one TENANT_ADMIN."""

    def _make(slug: str = "acme") -> Org:
        tenant = tenant_factory(slug=slug)
        staff = user_factory(
            tenant, email=f"rahul@{slug}.com", employee_code="EMP-1",
            name="Rahul Sharma", role=UserRole.STAFF,
        )
        manager = user_factory(
            tenant, email=f"manager@{slug}.com", employee_code="MGR-1",
            name="Priya Menon", role=UserRole.MANAGER,
        )
        admin = user_factory(
            tenant, email=f"admin@{slug}.com", employee_code="ADM-1",
            name="Arun Das", role=UserRole.TENANT_ADMIN,
        )
        return Org(
            tenant=tenant,
            staff=staff,
            manager=manager,
            admin=admin,
            staff_token=login(slug, f"rahul@{slug}.com").json()["access_token"],
            manager_token=login(slug, f"manager@{slug}.com").json()["access_token"],
            admin_token=login(slug, f"admin@{slug}.com").json()["access_token"],
        )

    return _make


# ---------------------------------------------------------------------------
# 4-5, 44. RBAC
# ---------------------------------------------------------------------------


def test_staff_cannot_reach_tenant_wide_endpoints(
    client: TestClient, org: Callable[..., Org]
) -> None:
    o = org()
    headers = auth_header(o.staff_token)

    for url in (TEAM_URL, user_url(o.manager.id), user_history_url(o.manager.id)):
        response = client.get(url, headers=headers)
        assert response.status_code == 403, url
        assert response.json()["detail"] == "Insufficient permissions"


def test_staff_cannot_read_a_colleague_even_their_own_id(
    client: TestClient, org: Callable[..., Org]
) -> None:
    """403 comes from the role gate, before any id is considered."""
    o = org()

    response = client.get(user_url(o.staff.id), headers=auth_header(o.staff_token))

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["manager", "admin"])
def test_manager_and_admin_can_read_team_and_users(
    client: TestClient, org: Callable[..., Org], role: str
) -> None:
    o = org()
    token = o.manager_token if role == "manager" else o.admin_token

    assert client.get(TEAM_URL, headers=auth_header(token)).status_code == 200
    assert client.get(user_url(o.staff.id), headers=auth_header(token)).status_code == 200
    assert (
        client.get(user_history_url(o.staff.id), headers=auth_header(token)).status_code
        == 200
    )


def test_managers_can_still_read_their_own_attendance(
    client: TestClient, org: Callable[..., Org]
) -> None:
    o = org()

    body = client.get(
        "/api/v1/attendance/me", headers=auth_header(o.manager_token)
    ).json()

    assert body["user_id"] == str(o.manager.id)


def test_team_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get(TEAM_URL).status_code == 401
    assert client.get(user_url(uuid.uuid4())).status_code == 401
    assert client.get(user_history_url(uuid.uuid4())).status_code == 401


# ---------------------------------------------------------------------------
# 17-19, 34. Team dashboard
# ---------------------------------------------------------------------------


def test_team_lists_every_active_user_including_those_without_events(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """Somebody with no attendance is exactly who a manager is looking for."""
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))  # COMPLETED
    attendance_event_factory(
        o.manager,
        event_type=AttendanceEventType.CHECK_IN,
        at=datetime.combine(TODAY, time(9), tzinfo=UTC),
    )  # CHECKED_IN
    # admin has nothing -> NO_RECORD

    body = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()

    assert body["date"] == TODAY.isoformat()
    by_id = {e["user_id"]: e for e in body["employees"]}
    assert set(by_id) == {str(o.staff.id), str(o.manager.id), str(o.admin.id)}
    assert by_id[str(o.staff.id)]["status"] == "COMPLETED"
    assert by_id[str(o.manager.id)]["status"] == "CHECKED_IN"
    assert by_id[str(o.admin.id)]["status"] == "NO_RECORD"
    assert by_id[str(o.admin.id)]["check_in"] is None
    assert by_id[str(o.staff.id)]["name"] == "Rahul Sharma"
    assert by_id[str(o.staff.id)]["employee_code"] == "EMP-1"


def test_team_summary_counts_add_up(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))
    attendance_event_factory(
        o.manager,
        event_type=AttendanceEventType.CHECK_IN,
        at=datetime.combine(TODAY, time(9), tzinfo=UTC),
    )

    summary = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()["summary"]

    assert summary == {
        "total_staff": 3,
        "no_record": 1,
        "checked_in": 1,
        "completed": 1,
    }
    assert (
        summary["no_record"] + summary["checked_in"] + summary["completed"]
        == summary["total_staff"]
    )


def test_team_excludes_inactive_users_but_history_keeps_them(
    client: TestClient,
    db_session: Session,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """A departed employee leaves the dashboard but keeps their record."""
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))
    o.staff.status = UserStatus.INACTIVE.value
    db_session.flush()

    team = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()
    assert str(o.staff.id) not in {e["user_id"] for e in team["employees"]}
    assert team["summary"]["total_staff"] == 2

    # Their history is still fully available to an authorised viewer.
    history = client.get(
        user_history_url(o.staff.id), headers=auth_header(o.manager_token)
    )
    assert history.status_code == 200
    assert any(item["status"] == "COMPLETED" for item in history.json()["items"])


def test_team_ordering_is_deterministic_for_identical_names(
    client: TestClient,
    org: Callable[..., Org],
    user_factory: Callable[..., User],
) -> None:
    """Two people called the same must still come back in a stable order."""
    o = org()
    for code in ("Z-9", "A-1", "M-5"):
        user_factory(
            o.tenant,
            email=f"same{code}@acme.com",
            employee_code=code,
            name="Same Name",
            role=UserRole.STAFF,
        )

    first = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()
    second = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()

    assert [e["user_id"] for e in first["employees"]] == [
        e["user_id"] for e in second["employees"]
    ]
    same_named = [
        e["employee_code"] for e in first["employees"] if e["name"] == "Same Name"
    ]
    assert same_named == ["A-1", "M-5", "Z-9"]


def test_team_accepts_an_explicit_day(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    o = org()
    attendance_day_factory(o.staff, YESTERDAY, (9, 17))

    today = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()
    yesterday = client.get(
        TEAM_URL, params={"day": YESTERDAY.isoformat()}, headers=auth_header(o.manager_token)
    ).json()

    assert today["summary"]["completed"] == 0
    assert yesterday["summary"]["completed"] == 1
    assert yesterday["date"] == YESTERDAY.isoformat()


# ---------------------------------------------------------------------------
# 51. No N+1
# ---------------------------------------------------------------------------


def test_team_query_count_does_not_grow_with_headcount(
    client: TestClient,
    engine: Engine,
    org: Callable[..., Org],
    user_factory: Callable[..., User],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """The dashboard must not issue one query per employee.

    Counted at the driver, so an accidental lazy-load would show up.
    """
    o = org()
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def measure() -> int:
        statements.clear()
        event.listen(engine, "before_cursor_execute", record)
        try:
            response = client.get(TEAM_URL, headers=auth_header(o.manager_token))
            assert response.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        # Auth costs a fixed lookup; the team work itself is the roster + events.
        return len(statements)

    small = measure()

    for index in range(25):
        extra = user_factory(
            o.tenant,
            email=f"extra{index}@acme.com",
            employee_code=f"X-{index:03d}",
            name=f"Extra {index}",
            role=UserRole.STAFF,
        )
        attendance_day_factory(extra, TODAY, (9, 17))

    large = measure()

    body = client.get(TEAM_URL, headers=auth_header(o.manager_token)).json()
    assert body["summary"]["total_staff"] == 28
    # 28 employees instead of 3 must not cost 25 more statements.
    assert large == small, f"query count grew from {small} to {large} (N+1)"
    assert large <= 5, f"unexpectedly many statements: {large}"


# ---------------------------------------------------------------------------
# 15-16, 20-25, 31, 43. Individual lookup and cross-tenant isolation
# ---------------------------------------------------------------------------


def test_manager_can_read_a_same_tenant_user(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))

    body = client.get(user_url(o.staff.id), headers=auth_header(o.manager_token)).json()

    assert body["user_id"] == str(o.staff.id)
    assert body["day"]["status"] == "COMPLETED"
    assert body["state"] == "NOT_CHECKED_IN"


def test_manager_can_read_a_same_tenant_user_history(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    o = org()
    attendance_day_factory(o.staff, YESTERDAY, (9, 17))

    body = client.get(
        user_history_url(o.staff.id),
        params={"from_date": YESTERDAY.isoformat(), "to_date": TODAY.isoformat()},
        headers=auth_header(o.manager_token),
    ).json()

    assert body["user_id"] == str(o.staff.id)
    assert [i["status"] for i in body["items"]] == ["NO_RECORD", "COMPLETED"]


@pytest.mark.parametrize("viewer", ["manager_token", "admin_token"])
def test_cross_tenant_user_lookup_returns_404_not_403(
    client: TestClient, org: Callable[..., Org], viewer: str
) -> None:
    """404 for another tenant's id - identical to an id that does not exist.

    A 403 would confirm the id is real somewhere and make this a tenant-wide
    enumeration oracle.
    """
    acme = org(slug="acme")
    beta = org(slug="beta")
    token = getattr(acme, viewer)

    real_other_tenant = client.get(user_url(beta.staff.id), headers=auth_header(token))
    pure_fiction = client.get(user_url(uuid.uuid4()), headers=auth_header(token))

    assert real_other_tenant.status_code == 404
    assert pure_fiction.status_code == 404
    # Indistinguishable, byte for byte.
    assert real_other_tenant.json() == pure_fiction.json() == {"detail": "User not found"}


def test_cross_tenant_history_is_also_404(
    client: TestClient, org: Callable[..., Org]
) -> None:
    acme = org(slug="acme")
    beta = org(slug="beta")

    response = client.get(
        user_history_url(beta.staff.id), headers=auth_header(acme.manager_token)
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_team_never_includes_another_tenants_staff(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    acme = org(slug="acme")
    beta = org(slug="beta")
    attendance_day_factory(acme.staff, TODAY, (9, 17))
    attendance_day_factory(beta.staff, TODAY, (10, 18))

    acme_team = client.get(TEAM_URL, headers=auth_header(acme.manager_token))
    beta_team = client.get(TEAM_URL, headers=auth_header(beta.manager_token))

    acme_ids = {e["user_id"] for e in acme_team.json()["employees"]}
    beta_ids = {e["user_id"] for e in beta_team.json()["employees"]}

    assert acme_ids == {str(acme.staff.id), str(acme.manager.id), str(acme.admin.id)}
    assert beta_ids == {str(beta.staff.id), str(beta.manager.id), str(beta.admin.id)}
    assert acme_ids.isdisjoint(beta_ids)
    # Nothing about the other tenant appears anywhere in the payload.
    assert str(beta.staff.id) not in acme_team.text
    assert "beta" not in acme_team.text.lower()


def test_tenant_cannot_be_widened_by_query_or_header(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    acme = org(slug="acme")
    beta = org(slug="beta")
    attendance_day_factory(beta.staff, TODAY, (10, 18))

    response = client.get(
        TEAM_URL,
        params={"tenant_id": str(beta.tenant.id), "include_inactive": "true"},
        headers={
            **auth_header(acme.manager_token),
            "X-Tenant-Id": str(beta.tenant.id),
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"]["total_staff"] == 3
    assert str(beta.staff.id) not in response.text


def test_a_users_events_never_leak_across_tenants_by_id_reuse(
    client: TestClient,
    db_session: Session,
    org: Callable[..., Org],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """Queries are scoped by tenant *and* user, not user alone."""
    acme = org(slug="acme")
    beta = org(slug="beta")
    attendance_event_factory(
        beta.staff,
        event_type=AttendanceEventType.CHECK_IN,
        at=datetime.combine(TODAY, time(9), tzinfo=UTC),
    )

    # Acme's manager asks about their own staff: must see nothing of Beta's.
    body = client.get(
        user_url(acme.staff.id), headers=auth_header(acme.manager_token)
    ).json()

    assert body["day"]["status"] == "NO_RECORD"
    total = db_session.scalar(select(func.count()).select_from(AttendanceEvent))
    assert total == 1  # Beta's event exists, it simply is not visible here


# ---------------------------------------------------------------------------
# 47. Reads never mutate
# ---------------------------------------------------------------------------


def test_team_reads_create_no_attendance_events(
    client: TestClient,
    db_session: Session,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))
    before = db_session.scalar(select(func.count()).select_from(AttendanceEvent))

    for _ in range(3):
        client.get(TEAM_URL, headers=auth_header(o.manager_token))
        client.get(user_url(o.staff.id), headers=auth_header(o.manager_token))
        client.get(user_history_url(o.staff.id), headers=auth_header(o.manager_token))

    db_session.expire_all()
    after = db_session.scalar(select(func.count()).select_from(AttendanceEvent))
    assert after == before == 2


def test_team_response_exposes_no_contact_or_credential_data(
    client: TestClient,
    org: Callable[..., Org],
    attendance_day_factory: Callable[..., tuple[AttendanceEvent, ...]],
) -> None:
    """A dashboard needs names, not inboxes or hashes."""
    o = org()
    attendance_day_factory(o.staff, TODAY, (9, 17))

    text = client.get(TEAM_URL, headers=auth_header(o.manager_token)).text.lower()

    for leaked in (
        "email",
        "@acme.com",
        "password",
        "$argon2",
        "nonce",
        "latitude",
        "distance",
        "role",
    ):
        assert leaked not in text, leaked
