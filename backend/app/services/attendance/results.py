"""Result types for the attendance lifecycle.

Mirrors the layout of :mod:`app.services.presence.results`: enums and dataclasses
with no service dependencies, so nothing here can create an import cycle.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
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
