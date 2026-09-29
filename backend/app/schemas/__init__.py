"""Pydantic request/response models (the API contract)."""

from app.schemas.attendance import (
    AttendanceActionRequest,
    AttendanceActionResponse,
    AttendanceDayResponse,
    AttendanceHistoryResponse,
    AttendanceSessionResponse,
    AttendanceTodayResponse,
    PaginationResponse,
    PresenceSummary,
    TeamAttendanceMember,
    TeamAttendanceResponse,
    TeamAttendanceSummary,
    TeamHoursResponse,
    TeamHoursTotals,
    TeamMemberHoursResponse,
)
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.presence import (
    GPSVerificationResult,
    PresenceVerificationRequest,
    PresenceVerificationResponse,
    QRVerificationResult,
)
from app.schemas.user import UserResponse

__all__ = [
    # attendance
    "AttendanceActionRequest",
    "AttendanceActionResponse",
    "AttendanceDayResponse",
    "AttendanceHistoryResponse",
    "AttendanceSessionResponse",
    "AttendanceTodayResponse",
    "PaginationResponse",
    "PresenceSummary",
    "TeamAttendanceMember",
    "TeamAttendanceResponse",
    "TeamAttendanceSummary",
    "TeamHoursResponse",
    "TeamHoursTotals",
    "TeamMemberHoursResponse",
    # auth
    "LoginRequest",
    "RefreshTokenRequest",
    "TokenResponse",
    "UserResponse",
    # presence
    "GPSVerificationResult",
    "PresenceVerificationRequest",
    "PresenceVerificationResponse",
    "QRVerificationResult",
]
