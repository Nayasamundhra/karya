"""Attendance lifecycle: the only place that writes ``attendance_events``.

* :mod:`results` - state machine enums and the outcome dataclass
* :mod:`service` - check-in / check-out, state derivation, audit logging

Presence is re-verified inside every action through
:mod:`app.services.presence`; no GPS or QR logic is duplicated here.
"""

from app.services.attendance.results import (
    AttendanceFailureReason,
    AttendanceOutcome,
    AttendanceState,
)
from app.services.attendance.service import (
    check_in,
    check_out,
    get_current_state,
    get_latest_event,
    record_attendance,
)

__all__ = [
    "AttendanceFailureReason",
    "AttendanceOutcome",
    "AttendanceState",
    "check_in",
    "check_out",
    "get_current_state",
    "get_latest_event",
    "record_attendance",
]
