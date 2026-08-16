"""Request/response schemas for presence verification.

The request model is the security boundary. It accepts *evidence only* -
coordinates, accuracy, a challenge id and a nonce - and sets ``extra="forbid"``
so an attempt to smuggle in ``tenant_id``, ``user_id``, ``gps_verified``,
``qr_verified``, ``presence_verified`` or ``distance_meters`` is rejected with a
422 rather than silently ignored. Loud refusal beats quiet discard: it makes a
spoofing attempt visible instead of leaving the caller believing it worked.

Every verified/derived value in the response is computed by the server.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.presence.results import (
    FailureReason,
    PresenceDecision,
    PresenceStatus,
)
from app.services.presence.service import client_facing_reason

#: Matches `qr_challenges.nonce VARCHAR(255)`.
_NONCE_MAX_LENGTH = 255


class QRChallengeResponse(BaseModel):
    """A freshly issued challenge, for the office display to render as a QR.

    The display encodes ``challenge_id`` and ``nonce`` into the QR image; those
    two are all a phone needs to submit. Nothing else about the tenant, the
    location or its coordinates is included - the server stays authoritative and
    the QR stays compact.
    """

    model_config = ConfigDict(extra="forbid")

    challenge_id: uuid.UUID
    nonce: str
    expires_at: datetime
    #: Seconds of validity, so the display can schedule its next fetch without
    #: doing clock arithmetic against a server timestamp.
    expires_in: int


class PresenceVerificationRequest(BaseModel):
    """Evidence submitted by a staff device.

    Note what is absent: no identity, no tenant, no verdict, no distance. All of
    those are derived from the bearer token and the database.
    """

    model_config = ConfigDict(extra="forbid")

    # allow_inf_nan=False rejects NaN/Infinity, which would otherwise slip past
    # a range check (every comparison against NaN is False).
    latitude: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)
    longitude: float = Field(ge=-180.0, le=180.0, allow_inf_nan=False)
    #: Device-reported accuracy radius in metres. Stored and evaluated, never
    #: trusted as a verdict.
    accuracy_meters: float = Field(ge=0.0, allow_inf_nan=False)
    challenge_id: uuid.UUID
    nonce: str = Field(min_length=1, max_length=_NONCE_MAX_LENGTH)


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
    """QR challenge outcome. Deliberately carries no nonce."""

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
    #: response cannot be used to test whether an id exists in another tenant.
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
