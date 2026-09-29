"""ORM models.

Importing this package registers every model on ``Base.metadata``, which is
what Alembic autogenerate and the test suite rely on. Import order matters only
in that every module must be imported before mapper configuration.
"""

from app.models.attendance_event import (
    AttendanceEvent,
    AttendanceEventType,
    VerificationStatus,
)
from app.models.attendance_location import (
    DEFAULT_GEOFENCE_RADIUS_METERS,
    DEFAULT_MAX_SHIFT_HOURS,
    AttendanceLocation,
)
from app.models.audit_log import AuditLog
from app.models.email_verification_token import EmailVerificationToken
from app.models.refresh_token import RefreshToken
from app.models.tenant import Tenant
from app.models.user import User, UserRole, UserStatus

__all__ = [
    # Entities
    "AttendanceEvent",
    "AttendanceLocation",
    "AuditLog",
    "EmailVerificationToken",
    "RefreshToken",
    "Tenant",
    "User",
    # Value sets
    "AttendanceEventType",
    "UserRole",
    "UserStatus",
    "VerificationStatus",
    # Defaults
    "DEFAULT_GEOFENCE_RADIUS_METERS",
    "DEFAULT_MAX_SHIFT_HOURS",
]
