"""Request/response schemas for the attendance lifecycle.

The request **subclasses** the Phase 3 presence request rather than restating
its fields. That is not just brevity: it means the coordinate bounds, the
``allow_inf_nan=False`` guard and - most importantly - ``extra="forbid"`` are
defined once. If a future phase tightens presence validation, attendance
tightens with it automatically instead of quietly falling behind.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.attendance_event import AttendanceEventType
from app.schemas.presence import (
    GPSVerificationResult,
    PresenceVerificationRequest,
    QRVerificationResult,
)
from app.services.attendance.results import AttendanceOutcome, AttendanceState


class AttendanceActionRequest(PresenceVerificationRequest):
    """Evidence for a check-in or check-out.

    Identical to the presence contract: coordinates, accuracy, challenge id and
    nonce. Note what is *absent* - no user, no tenant, no timestamp, no event
    type and no verdict. Those are all determined by the server, and inherited
    ``extra="forbid"`` turns an attempt to supply one into a 422 rather than a
    silently ignored field.
    """


class PresenceSummary(BaseModel):
    """The presence evidence behind an attendance decision."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    gps: GPSVerificationResult
    qr: QRVerificationResult


class AttendanceActionResponse(BaseModel):
    """The outcome of a check-in or check-out attempt.

    A refusal is reported as ``success: false`` with HTTP 200, matching
    ``/presence/verify``. The request was well-formed and fully processed; the
    answer is "no, and here is exactly why". Returning the presence breakdown
    alongside the reason is what lets a client tell the user *"you are 350 m
    away"* rather than just *"failed"*. HTTP error codes stay reserved for
    requests that could not be processed at all - 401 unauthenticated, 422
    malformed or smuggled fields.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    #: The action attempted, regardless of outcome.
    event_type: AttendanceEventType
    #: The user's attendance state *after* the attempt. On a rejection this is
    #: the unchanged current state, which usually explains the rejection.
    status: AttendanceState
    #: Present only on success - a refusal writes no row.
    attendance_event_id: uuid.UUID | None = None
    #: Server-generated (PostgreSQL ``now()``), never the device clock.
    event_timestamp: datetime | None = None
    #: ``None`` when the attempt was refused on state grounds before any
    #: evidence was examined.
    presence: PresenceSummary | None = None
    reason: str | None = None

    @classmethod
    def from_outcome(cls, outcome: AttendanceOutcome) -> AttendanceActionResponse:
        """Build the wire response from a service outcome."""
        presence = None
        if outcome.presence is not None:
            decision = outcome.presence
            presence = PresenceSummary(
                verified=decision.verified,
                gps=GPSVerificationResult(
                    verified=decision.gps.verified,
                    distance_meters=(
                        round(decision.gps.distance_meters, 2)
                        if decision.gps.distance_meters is not None
                        else None
                    ),
                    accuracy_meters=decision.gps.accuracy_meters,
                ),
                qr=QRVerificationResult(verified=decision.qr.verified),
            )

        return cls(
            success=outcome.success,
            event_type=outcome.event_type,
            status=outcome.state,
            attendance_event_id=outcome.event_id,
            event_timestamp=outcome.event_timestamp,
            presence=presence,
            reason=outcome.reason.value if outcome.reason is not None else None,
        )
