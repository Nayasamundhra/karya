"""Attendance: the only place that writes - and reads - ``attendance_events``.

* :mod:`results` - state machine enums, outcome and read models
* :mod:`service` - check-in / check-out (the only writer)
* :mod:`queries` - read-only history, daily and team views

Presence is re-verified inside every write through
:mod:`app.services.presence`; no GPS or QR logic is duplicated here. The read
side adds no tables and no cached status: every state is derived from the events.
"""

from app.services.attendance.queries import (
    get_day,
    get_history,
    get_team_day,
    find_tenant_user,
)
from app.services.attendance.results import (
    AttendanceDay,
    AttendanceFailureReason,
    AttendanceHistoryPage,
    AttendanceOutcome,
    AttendanceSession,
    AttendanceState,
    DayStatus,
    TeamAttendance,
    TeamMemberDay,
)
from app.services.attendance.service import (
    check_in,
    check_out,
    get_current_state,
    get_latest_event,
    record_attendance,
)

__all__ = [
    # write
    "AttendanceFailureReason",
    "AttendanceOutcome",
    "AttendanceState",
    "check_in",
    "check_out",
    "get_current_state",
    "get_latest_event",
    "record_attendance",
    # read
    "AttendanceDay",
    "AttendanceHistoryPage",
    "AttendanceSession",
    "DayStatus",
    "TeamAttendance",
    "TeamMemberDay",
    "find_tenant_user",
    "get_day",
    "get_history",
    "get_team_day",
]
