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
)
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.presence import (
    GPSVerificationResult,
    PresenceVerificationRequest,
    PresenceVerificationResponse,
    QRChallengeResponse,
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
    # auth
    "LoginRequest",
    "RefreshTokenRequest",
    "TokenResponse",
    "UserResponse",
    # presence
    "GPSVerificationResult",
    "PresenceVerificationRequest",
    "PresenceVerificationResponse",
    "QRChallengeResponse",
    "QRVerificationResult",
]
