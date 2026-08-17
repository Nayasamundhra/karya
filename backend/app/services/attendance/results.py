"""Result types for the attendance lifecycle.

Mirrors the layout of :mod:`app.services.presence.results`: enums and dataclasses
with no service dependencies, so nothing here can create an import cycle.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime

from app.models.attendance_event import AttendanceEventType
from app.services.presence.results import FailureReason, PresenceDecision


class AttendanceState(enum.StrEnum):
    """A user's current attendance state.

    Derived from their most recent attendance event - there is deliberately no
    ``current_status`` column. A denormalised status would be a second source of
    truth that can drift from the events, and the events are the audit record
    that matters.

    ``CHECK_OUT`` returns a user to ``NOT_CHECKED_IN``, which is what allows
    repeated day-after-day cycles without any reset step.
    """

    NOT_CHECKED_IN = "NOT_CHECKED_IN"
    CHECKED_IN = "CHECKED_IN"


#: The state each event type leaves the user in.
STATE_AFTER_EVENT: dict[AttendanceEventType, AttendanceState] = {
    AttendanceEventType.CHECK_IN: AttendanceState.CHECKED_IN,
    AttendanceEventType.CHECK_OUT: AttendanceState.NOT_CHECKED_IN,
}

#: The state a user must be in for each event type to be legal.
STATE_REQUIRED_FOR_EVENT: dict[AttendanceEventType, AttendanceState] = {
    AttendanceEventType.CHECK_IN: AttendanceState.NOT_CHECKED_IN,
    AttendanceEventType.CHECK_OUT: AttendanceState.CHECKED_IN,
}


class AttendanceFailureReason(enum.StrEnum):
    """Why an attendance action was refused.

    Only the two state-transition reasons live here. Every presence-related
    refusal reuses :class:`app.services.presence.results.FailureReason` verbatim
    rather than being restated, so ``OUTSIDE_GEOFENCE`` means exactly the same
    thing whether it came from ``/presence/verify`` or ``/attendance/check-in``.
    """

    ALREADY_CHECKED_IN = "ALREADY_CHECKED_IN"
    NOT_CHECKED_IN = "NOT_CHECKED_IN"


#: Union of everything that can appear as a client-facing attendance reason.
AnyFailureReason = AttendanceFailureReason | FailureReason


@dataclass(frozen=True, slots=True)
class AttendanceOutcome:
    """The result of a check-in or check-out attempt.

    On success ``event_id`` and ``event_timestamp`` describe the row that was
    written; on failure both are ``None`` and no row exists.

    ``state`` is always the user's attendance state *after* the attempt, so a
    rejected request still tells the client where they actually stand - which is
    usually the thing that explains the rejection.
    """

    success: bool
    #: The action that was attempted, regardless of outcome.
    event_type: AttendanceEventType
    state: AttendanceState
    event_id: uuid.UUID | None = None
    event_timestamp: datetime | None = None
    reason: AnyFailureReason | None = None
    #: Present whenever presence was actually evaluated. ``None`` when the
    #: attempt was refused on state grounds before any evidence was examined.
    presence: PresenceDecision | None = None


# ---------------------------------------------------------------------------
# Phase 5 - read models
# ---------------------------------------------------------------------------


class DayStatus(enum.StrEnum):
    """How one calendar day looks for one user.

    ``NO_RECORD`` is named carefully. It states only that **no attendance event
    was recorded** for that day - it is *not* a claim that the person was absent
    from work. They may have been on leave, travelling, working elsewhere, or
    simply unable to reach the QR display; Karya has no way to tell, and leave
    and shift management do not exist yet. "ABSENT" would assert something the
    data does not support.

    Distinct from :class:`AttendanceState`, which is the *live* state machine
    Phase 4 uses to accept or refuse a check-in. This enum describes a completed
    (or in-progress) day and therefore needs the third ``COMPLETED`` value.
    """

    NO_RECORD = "NO_RECORD"
    CHECKED_IN = "CHECKED_IN"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class AttendanceSession:
    """One check-in/check-out pair within a day.

    Either side may be ``None``:

    * ``check_out is None`` - the session is still open.
    * ``check_in is None`` - the session opened on an *earlier* day and closed on
      this one. Phase 4 guarantees events alternate per user, but says nothing
      about calendar days, so a night shift legitimately produces a day whose
      first event is a CHECK_OUT. Dropping it would lose a real event.
    """

    check_in: datetime | None = None
    check_out: datetime | None = None
    check_in_event_id: uuid.UUID | None = None
    check_out_event_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class AttendanceDay:
    """One user's attendance for one UTC calendar day."""

    date: date_type
    status: DayStatus
    sessions: list[AttendanceSession] = field(default_factory=list)

    @property
    def first_check_in(self) -> datetime | None:
        """Earliest check-in of the day, if any."""
        for session in self.sessions:
            if session.check_in is not None:
                return session.check_in
        return None

    @property
    def last_check_out(self) -> datetime | None:
        """Latest check-out of the day, if any."""
        for session in reversed(self.sessions):
            if session.check_out is not None:
                return session.check_out
        return None


@dataclass(frozen=True, slots=True)
class AttendanceHistoryPage:
    """A page of consecutive days, newest first."""

    days: list[AttendanceDay]
    page: int
    page_size: int
    #: Total days in the requested range, not total events.
    total: int


@dataclass(frozen=True, slots=True)
class TeamMemberDay:
    """One colleague's day, for the tenant dashboard."""

    user_id: uuid.UUID
    name: str
    employee_code: str
    day: AttendanceDay


@dataclass(frozen=True, slots=True)
class TeamAttendance:
    """Today's attendance across one tenant.

    Every active user appears, including those with no events - a dashboard that
    silently omitted them would hide exactly the people a manager is looking for.
    """

    date: date_type
    members: list[TeamMemberDay]

    @property
    def total_staff(self) -> int:
        return len(self.members)

    def count(self, status: DayStatus) -> int:
        return sum(1 for member in self.members if member.day.status is status)
