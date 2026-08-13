"""ORM models.

Importing this package registers every model on ``Base.metadata``, which is
what Alembic autogenerate and the test suite rely on. Import order matters only
in that all six modules must be imported before mapper configuration.
"""

from app.models.attendance_event import (
    AttendanceEvent,
    AttendanceEventType,
    VerificationStatus,
)
from app.models.attendance_location import (
    DEFAULT_GEOFENCE_RADIUS_METERS,
    AttendanceLocation,
)
from app.models.audit_log import AuditLog
from app.models.qr_challenge import QRChallenge, QRChallengeStatus
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User, UserRole, UserStatus

__all__ = [
    # Entities
    "AttendanceEvent",
    "AttendanceLocation",
    "AuditLog",
    "QRChallenge",
    "RefreshToken",
    "Tenant",
    "User",
    # Value sets
    "AttendanceEventType",
    "QRChallengeStatus",
    "UserRole",
    "UserStatus",
    "VerificationStatus",
    # Defaults
    "DEFAULT_GEOFENCE_RADIUS_METERS",
]
