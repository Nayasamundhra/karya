"""Read-only attendance queries.

Nothing here writes: no INSERT, UPDATE or DELETE, and no ``session.commit()``.
``attendance_events`` stays the single source of truth - Phase 5 adds no status
table, no cached "current attendance" column and no derived storage of any kind.
Every state below is computed from the events on each request.

**Timezone.** Karya has no per-tenant timezone yet, so UTC is the canonical
calendar. That is not a detail to gloss over: the PostgreSQL session timezone on
a developer machine is whatever the OS says (``Asia/Calcutta`` here) while the
Docker image is configured ``UTC``. A bare ``date(event_timestamp)`` or
``::date`` would therefore silently bucket events by *different* days in the two
environments. So this module never asks SQL to derive a date. It filters on
explicit UTC instants and groups in Python via ``astimezone(UTC).date()``, which
gives the same answer everywhere. Per-tenant timezones are a later phase and
would slot in by replacing :func:`day_bounds` and :func:`utc_date_of`.

**Ranges are half-open** - ``[start, end)`` - so an event at exactly midnight
belongs to the day starting then, and no event can land in two buckets.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, date as date_type, datetime, time, timedelta

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.attendance_event import AttendanceEvent, AttendanceEventType
from app.models.user import User, UserStatus
from app.services.attendance.results import (
    AttendanceDay,
    AttendanceHistoryPage,
    AttendanceSession,
    DayStatus,
    TeamAttendance,
    TeamMemberDay,
)

#: Pagination and range guards. Without these a caller could ask for every event
#: a tenant has ever recorded in a single request.
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100
MAX_RANGE_DAYS = 366
#: Days of history returned when the caller supplies no explicit range.
DEFAULT_HISTORY_DAYS = 30


# ---------------------------------------------------------------------------
# UTC calendar helpers
# ---------------------------------------------------------------------------


def utc_today() -> date_type:
    """Today's date in UTC - never the machine's local date."""
    return datetime.now(UTC).date()


def utc_date_of(moment: datetime) -> date_type:
    """The UTC calendar date a timestamp falls on.

    ``astimezone`` is explicit rather than incidental: values read back from
    PostgreSQL carry the session's timezone offset (+05:30 locally, +00:00 under
    Docker), and ``.date()`` on the raw value would differ between the two.
    """
    return moment.astimezone(UTC).date()


def day_bounds(day: date_type) -> tuple[datetime, datetime]:
    """Half-open ``[00:00:00, next 00:00:00)`` UTC bounds for ``day``."""
    start = datetime.combine(day, time.min, tzinfo=UTC)
    return start, start + timedelta(days=1)


def range_bounds(from_date: date_type, to_date: date_type) -> tuple[datetime, datetime]:
    """Half-open UTC bounds covering ``from_date`` through ``to_date`` inclusive."""
    start, _ = day_bounds(from_date)
    _, end = day_bounds(to_date)
    return start, end


def dates_descending(from_date: date_type, to_date: date_type) -> list[date_type]:
    """Every date in the inclusive range, newest first."""
    span = (to_date - from_date).days
    return [to_date - timedelta(days=offset) for offset in range(span + 1)]


# ---------------------------------------------------------------------------
# Event loading
# ---------------------------------------------------------------------------


def _events_query(
    *,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    user_ids: Sequence[uuid.UUID] | None = None,
) -> Select[tuple[AttendanceEvent]]:
    """Events for a tenant in ``[start, end)``, optionally limited to users.

    ``tenant_id`` always constrains the query - it comes from the authenticated
    user, so no caller can widen it. Ordering is ``(user_id, event_timestamp,
    created_at)``: deterministic, and never dependent on UUID ordering or on
    PostgreSQL's physical row order.
    """
    query = select(AttendanceEvent).where(
        AttendanceEvent.tenant_id == tenant_id,
        AttendanceEvent.event_timestamp >= start,
        AttendanceEvent.event_timestamp < end,
    )
    if user_ids is not None:
        query = query.where(AttendanceEvent.user_id.in_(user_ids))
    return query.order_by(
        AttendanceEvent.user_id,
        AttendanceEvent.event_timestamp,
        AttendanceEvent.created_at,
    )


def load_events(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    user_ids: Sequence[uuid.UUID] | None = None,
) -> list[AttendanceEvent]:
    """Run :func:`_events_query`. One statement, whatever the user count."""
    return list(
        session.scalars(
            _events_query(
                tenant_id=tenant_id, start=start, end=end, user_ids=user_ids
            )
        )
    )


# ---------------------------------------------------------------------------
# Shaping events into days
# ---------------------------------------------------------------------------


def build_sessions(events: Iterable[AttendanceEvent]) -> list[AttendanceSession]:
    """Pair a single day's events, in order, into sessions.

    Handles the two ragged edges honestly rather than discarding events:

    * a leading CHECK_OUT closes a session that began on an earlier day, so it
      becomes a session with no ``check_in``;
    * a trailing CHECK_IN leaves a session open, with no ``check_out``.

    Phase 4's per-user alternation guarantee makes anything else impossible, but
    the loop is written so that unexpected input still round-trips every event
    into some session instead of silently dropping it.
    """
    sessions: list[AttendanceSession] = []
    open_event: AttendanceEvent | None = None

    for event in events:
        if event.event_type == AttendanceEventType.CHECK_IN:
            if open_event is not None:
                # Two check-ins in a row: close the first as open-ended rather
                # than losing it.
                sessions.append(
                    AttendanceSession(
                        check_in=open_event.event_timestamp,
                        check_in_event_id=open_event.id,
                    )
                )
            open_event = event
        else:  # CHECK_OUT
            sessions.append(
                AttendanceSession(
                    check_in=open_event.event_timestamp if open_event else None,
                    check_out=event.event_timestamp,
                    check_in_event_id=open_event.id if open_event else None,
                    check_out_event_id=event.id,
                )
            )
            open_event = None

    if open_event is not None:
        sessions.append(
            AttendanceSession(
                check_in=open_event.event_timestamp,
                check_in_event_id=open_event.id,
            )
        )
    return sessions


def build_day(day: date_type, events: Sequence[AttendanceEvent]) -> AttendanceDay:
    """Assemble one user's day from its (already ordered) events."""
    if not events:
        return AttendanceDay(date=day, status=DayStatus.NO_RECORD, sessions=[])

    sessions = build_sessions(events)
    # The last event decides the status: a trailing CHECK_IN means the person is
    # still checked in, anything else means every session is closed.
    last_is_check_in = events[-1].event_type == AttendanceEventType.CHECK_IN
    status = DayStatus.CHECKED_IN if last_is_check_in else DayStatus.COMPLETED
    return AttendanceDay(date=day, status=status, sessions=sessions)


def group_by_user_and_date(
    events: Iterable[AttendanceEvent],
) -> dict[tuple[uuid.UUID, date_type], list[AttendanceEvent]]:
    """Bucket events by ``(user_id, UTC date)``, preserving order."""
    grouped: dict[tuple[uuid.UUID, date_type], list[AttendanceEvent]] = {}
    for event in events:
        key = (event.user_id, utc_date_of(event.event_timestamp))
        grouped.setdefault(key, []).append(event)
    return grouped


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------


def get_day(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    day: date_type | None = None,
) -> AttendanceDay:
    """One user's attendance for one day (default: today, UTC).

    Uses the Phase 1 ``(tenant_id, user_id, event_timestamp)`` index directly:
    equality on the first two columns, a range on the third.
    """
    day = day or utc_today()
    start, end = day_bounds(day)
    events = load_events(
        session, tenant_id=tenant_id, start=start, end=end, user_ids=[user_id]
    )
    return build_day(day, events)


def get_history(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    from_date: date_type,
    to_date: date_type,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> AttendanceHistoryPage:
    """A page of one user's daily attendance, newest day first.

    Days are the unit of pagination, and **every** date in the requested range is
    returned - including days with no events, as ``NO_RECORD``. A calendar view
    needs the gaps; returning only days that happen to have rows would make it
    impossible to tell "nothing recorded" from "beyond the range".

    Because the page is a slice of a known date range, the total is arithmetic
    rather than a second COUNT query, and only the visible window's events are
    loaded.
    """
    all_dates = dates_descending(from_date, to_date)
    total = len(all_dates)

    offset = (page - 1) * page_size
    window = all_dates[offset : offset + page_size]
    if not window:
        return AttendanceHistoryPage(
            days=[], page=page, page_size=page_size, total=total
        )

    # `window` is contiguous and descending, so its span is one range query.
    start, end = range_bounds(window[-1], window[0])
    events = load_events(
        session, tenant_id=tenant_id, start=start, end=end, user_ids=[user_id]
    )
    grouped = group_by_user_and_date(events)

    days = [build_day(day, grouped.get((user_id, day), [])) for day in window]
    return AttendanceHistoryPage(
        days=days, page=page, page_size=page_size, total=total
    )


def get_team_day(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    day: date_type | None = None,
    include_inactive: bool = False,
) -> TeamAttendance:
    """Every active user in the tenant, with their attendance for ``day``.

    **Exactly two queries, regardless of headcount** - one for the roster and one
    for the day's events, joined in Python. The obvious alternative (fetch users,
    then query each user's events) is an N+1 that would issue one statement per
    employee on the endpoint most likely to be polled by a dashboard.

    Inactive users are excluded by default: the dashboard answers "who is at work
    today", and a departed employee is noise there. Their history remains fully
    queryable through :func:`get_history` - Phase 5 deletes nothing.
    """
    day = day or utc_today()
    start, end = day_bounds(day)

    roster_query = select(User).where(User.tenant_id == tenant_id)
    if not include_inactive:
        roster_query = roster_query.where(User.status == UserStatus.ACTIVE)
    # Stable ordering: name, then employee_code to break ties between people who
    # share a name.
    roster = list(
        session.scalars(roster_query.order_by(User.name, User.employee_code))
    )

    events = load_events(
        session,
        tenant_id=tenant_id,
        start=start,
        end=end,
        user_ids=[user.id for user in roster] or None,
    )
    grouped = group_by_user_and_date(events)

    members = [
        TeamMemberDay(
            user_id=user.id,
            name=user.name,
            employee_code=user.employee_code,
            day=build_day(day, grouped.get((user.id, day), [])),
        )
        for user in roster
    ]
    return TeamAttendance(date=day, members=members)


def find_tenant_user(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> User | None:
    """Look up a user **within the caller's tenant**.

    Returns ``None`` both for "no such user" and "belongs to another tenant", so
    a caller cannot distinguish them. Answering 403 for the second case would
    confirm the id exists somewhere and turn this into a tenant-wide enumeration
    oracle; the route turns ``None`` into an ordinary 404.
    """
    return session.scalar(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
