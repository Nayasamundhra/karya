"""Presence verification: is this staff member physically at their site?

Module split:

* :mod:`results` - shared enums and result dataclasses (no dependencies)
* :mod:`gps`     - coordinate validation, haversine distance, geofence check
* :mod:`qr`      - challenge creation, validation, atomic single-use consumption
* :mod:`service` - combines both signals into one decision, plus audit logging

Phase 3 answers only "is Rahul present?". It never writes an ``AttendanceEvent``
- turning verified presence into a check-in or check-out is Phase 4.
"""

from app.services.presence.results import (
    FailureReason,
    GPSResult,
    PresenceDecision,
    PresenceStatus,
    QRResult,
    to_client_reason,
)
from app.services.presence.service import (
    NoActiveAttendanceLocationError,
    get_active_attendance_location,
    issue_qr_challenge,
    verify_presence,
)

__all__ = [
    # results
    "FailureReason",
    "GPSResult",
    "PresenceDecision",
    "PresenceStatus",
    "QRResult",
    "to_client_reason",
    # flows
    "NoActiveAttendanceLocationError",
    "get_active_attendance_location",
    "issue_qr_challenge",
    "verify_presence",
]
