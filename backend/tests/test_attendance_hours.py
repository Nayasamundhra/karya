"""Team hours-worked reads: ``GET /attendance/team/hours``.

Covers RBAC/shape at the HTTP layer and the clipping arithmetic (open
sessions, auto-closed sessions, week/month boundaries) directly against
``app.services.attendance.queries.get_team_hours``, the same split
``test_attendance_read.py`` uses for boundary-precise cases that need an
explicit ``now`` a live HTTP request can't hand in.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.models import AttendanceEvent, AttendanceEventType, Tenant, User, UserRole
from app.services.attendance import queries
from tests.conftest import auth_header

HOURS_URL = "/api/v1/attendance/team/hours"
TODAY = queries.utc_today()
WEEK_START = queries.week_start_of(TODAY)
MONTH_START = queries.month_start_of(TODAY)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=UTC)


@pytest.fixture
def org(
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
):
    tenant = tenant_factory(slug="acme")
    staff = user_factory(
        tenant, email="rahul@acme.com", employee_code="EMP-1",
        name="Rahul Sharma", role=UserRole.STAFF,
    )
    manager = user_factory(
        tenant, email="manager@acme.com", employee_code="MGR-1",
        name="Priya Menon", role=UserRole.MANAGER,
    )
    return {
        "tenant": tenant,
        "staff": staff,
        "manager": manager,
        "manager_token": login("acme", "manager@acme.com").json()["access_token"],
        "staff_token": login("acme", "rahul@acme.com").json()["access_token"],
    }


# ---------------------------------------------------------------------------
# HTTP layer: RBAC and shape
# ---------------------------------------------------------------------------


def test_requires_authentication(client: TestClient) -> None:
    assert client.get(HOURS_URL).status_code == 401


def test_staff_cannot_read_team_hours(client: TestClient, org) -> None:
    response = client.get(HOURS_URL, headers=auth_header(org["staff_token"]))
    assert response.status_code == 403


def test_manager_gets_a_summary_and_per_employee_figures(
    client: TestClient,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """This hits the live endpoint, which reads ``datetime.now(UTC)`` itself
    with no injectable clock - unlike the query-layer tests below, a session
    close to real "now" risks straddling the UTC midnight/week/month
    boundary depending on what instant the suite happens to run at. So this
    only checks shape and internal consistency; the precise clipping
    arithmetic is covered with an injected ``now`` below.
    """
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 0, 1)
    )

    body = client.get(HOURS_URL, headers=auth_header(org["manager_token"])).json()

    assert body["date"] == TODAY.isoformat()
    assert body["week_start"] == WEEK_START.isoformat()
    assert body["month_start"] == MONTH_START.isoformat()
    by_id = {e["user_id"]: e for e in body["employees"]}
    staff_hours = by_id[str(org["staff"].id)]
    assert staff_hours["today_hours"] >= 0
    assert staff_hours["today_hours"] <= staff_hours["week_hours"] <= staff_hours["month_hours"]
    assert body["summary"]["total_today_hours"] == pytest.approx(
        sum(e["today_hours"] for e in body["employees"])
    )
    assert body["summary"]["total_month_hours"] == pytest.approx(
        sum(e["month_hours"] for e in body["employees"])
    )


def test_team_hours_never_leaks_another_tenant(
    client: TestClient,
    org,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    login: Callable[..., Response],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    beta = tenant_factory(slug="beta")
    beta_staff = user_factory(
        beta, email="x@beta.com", employee_code="B-1", role=UserRole.STAFF
    )
    attendance_event_factory(
        beta_staff, event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )

    response = client.get(HOURS_URL, headers=auth_header(org["manager_token"]))

    assert response.status_code == 200
    assert str(beta_staff.id) not in response.text


# ---------------------------------------------------------------------------
# Query-layer: clipping arithmetic, with an explicit `now`
# ---------------------------------------------------------------------------


def test_completed_session_counts_its_full_duration(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 17)
    )

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 20)
    )

    member = next(m for m in result.members if m.user_id == org["staff"].id)
    assert member.today_hours == pytest.approx(8.0)


def test_open_session_clips_to_now_and_grows_over_time(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """Nobody has checked this person out yet - the figure is "so far"."""
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )

    two_hours_in = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 11)
    )
    five_hours_in = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 14)
    )

    member_at_2h = next(
        m for m in two_hours_in.members if m.user_id == org["staff"].id
    )
    member_at_5h = next(
        m for m in five_hours_in.members if m.user_id == org["staff"].id
    )
    assert member_at_2h.today_hours == pytest.approx(2.0)
    assert member_at_5h.today_hours == pytest.approx(5.0)


def test_auto_closed_session_counts_to_its_checkout_not_to_now(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """An auto-closed shift is a *closed* session - it must not keep growing
    just because nobody has checked in since."""
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )
    attendance_event_factory(
        org["staff"],
        event_type=AttendanceEventType.CHECK_OUT,
        at=at(TODAY, 17),
        verification_status="AUTO_CLOSED",
    )

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 23)
    )

    member = next(m for m in result.members if m.user_id == org["staff"].id)
    assert member.today_hours == pytest.approx(8.0)


def test_week_boundary_clips_but_month_keeps_the_full_session(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """A session that finished earlier this month but *before* this week
    started counts toward the month total and not the week total."""
    if WEEK_START <= MONTH_START:
        pytest.skip("needs a day where this week starts after the month does")

    earlier_this_month = WEEK_START - timedelta(days=1)
    attendance_event_factory(
        org["staff"],
        event_type=AttendanceEventType.CHECK_IN,
        at=at(earlier_this_month, 9),
    )
    attendance_event_factory(
        org["staff"],
        event_type=AttendanceEventType.CHECK_OUT,
        at=at(earlier_this_month, 17),
    )

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 12)
    )

    member = next(m for m in result.members if m.user_id == org["staff"].id)
    assert member.week_hours == pytest.approx(0.0)
    assert member.month_hours == pytest.approx(8.0)


def test_session_spanning_into_the_window_is_clipped_not_dropped(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    """A shift that started yesterday and ended after midnight must not be
    double-counted, nor silently dropped from today's total - only the
    portion inside today's window counts."""
    yesterday = TODAY - timedelta(days=1)
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(yesterday, 22)
    )
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 2)
    )

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 12)
    )

    member = next(m for m in result.members if m.user_id == org["staff"].id)
    assert member.today_hours == pytest.approx(2.0)  # midnight -> 02:00 only


def test_summary_totals_equal_the_sum_of_member_figures(
    db_session: Session,
    org,
    user_factory: Callable[..., User],
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 13)
    )
    second = user_factory(
        org["tenant"], email="second@acme.com", employee_code="EMP-2",
        role=UserRole.STAFF,
    )
    attendance_event_factory(
        second, event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )
    attendance_event_factory(
        second, event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 12)
    )

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 20)
    )

    assert result.total_today_hours == pytest.approx(
        sum(m.today_hours for m in result.members)
    )
    assert result.total_today_hours == pytest.approx(7.0)


def test_inactive_users_are_excluded_by_default(
    db_session: Session,
    org,
    attendance_event_factory: Callable[..., AttendanceEvent],
) -> None:
    from app.models import UserStatus

    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_IN, at=at(TODAY, 9)
    )
    attendance_event_factory(
        org["staff"], event_type=AttendanceEventType.CHECK_OUT, at=at(TODAY, 17)
    )
    org["staff"].status = UserStatus.INACTIVE.value
    db_session.flush()

    result = queries.get_team_hours(
        db_session, tenant_id=org["tenant"].id, now=at(TODAY, 20)
    )

    assert org["staff"].id not in {m.user_id for m in result.members}
