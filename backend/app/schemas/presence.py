"""Request/response schemas for presence verification.

The request model is the security boundary. It accepts *evidence only* -
coordinates, accuracy and a QR token - and sets ``extra="forbid"`` so an
attempt to smuggle in ``tenant_id``, ``user_id``, ``gps_verified``,
``qr_verified``, ``presence_verified`` or ``distance_meters`` is rejected with
a 422 rather than silently ignored. Loud refusal beats quiet discard: it
makes a spoofing attempt visible instead of leaving the caller believing it
worked.

Every verified/derived value in the response is computed by the server.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.services.presence.results import (
    FailureReason,
    PresenceDecision,
    PresenceStatus,
)
from app.services.presence.service import client_facing_reason


class PresenceVerificationRequest(BaseModel):
    """Evidence submitted by a staff device.

    Note what is absent: no identity, no tenant, no verdict, no distance. All
    of those are derived from the bearer token and the database.
    ``qr_token`` is the static value printed/displayed at the office - it
    never expires and is the same on every scan, so nothing here needs a
    nonce or a challenge id any more.
    """

    model_config = ConfigDict(extra="forbid")

    # allow_inf_nan=False rejects NaN/Infinity, which would otherwise slip past
    # a range check (every comparison against NaN is False).
    latitude: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)
    longitude: float = Field(ge=-180.0, le=180.0, allow_inf_nan=False)
    #: Device-reported accuracy radius in metres. Stored and evaluated, never
    #: trusted as a verdict.
    accuracy_meters: float = Field(ge=0.0, allow_inf_nan=False)
    qr_token: uuid.UUID


class GPSVerificationResult(BaseModel):
    """Server-computed GPS outcome."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    #: Server-calculated great-circle distance to the attendance location.
    #: ``None`` only when coordinates were unusable. The office's own
    #: coordinates are never returned - a distance is all the client needs, and
    #: revealing the site's exact position would help someone spoof it.
    distance_meters: float | None
    accuracy_meters: float


class QRVerificationResult(BaseModel):
    """QR-token resolution outcome. Deliberately carries no location detail."""

    model_config = ConfigDict(extra="forbid")

    verified: bool


class PresenceVerificationResponse(BaseModel):
    """The presence decision returned to the caller."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    status: PresenceStatus
    gps: GPSVerificationResult
    qr: QRVerificationResult
    #: Populated only on rejection, and only with a client-safe value: internal
    #: reasons such as QR_TENANT_MISMATCH collapse to QR_NOT_FOUND so the
    #: response cannot be used to test whether a location exists in another
    #: tenant.
    reason: FailureReason | None = None

    @classmethod
    def from_decision(cls, decision: PresenceDecision) -> PresenceVerificationResponse:
        """Build the wire response from a service decision."""
        return cls(
            verified=decision.verified,
            status=decision.status,
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
            reason=client_facing_reason(decision),
        )
