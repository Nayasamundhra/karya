"""Result types shared by the presence-verification modules.

These live in their own module so ``gps.py`` and ``qr.py`` can produce typed
results without importing ``service.py`` (which imports them) - no import cycle.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from typing import Any, Final


class PresenceStatus(enum.StrEnum):
    """Outcome of a presence-verification attempt.

    Only two outcomes exist in Phase 3. ``MANUAL_REVIEW`` deliberately does not
    appear here: it belongs to ``AttendanceEvent.verification_status``, where
    Phase 4 can apply policy to a rejected-but-plausible attempt. Adding a third
    presence outcome now would be complexity with no consumer.
    """

    PRESENCE_VERIFIED = "PRESENCE_VERIFIED"
    PRESENCE_REJECTED = "PRESENCE_REJECTED"


class FailureReason(enum.StrEnum):
    """Why a presence attempt was rejected.

    Some values are internal-only; see :data:`CLIENT_SAFE_REASON` for the
    mapping applied before a reason reaches an API response.
    """

    # --- Location ---
    NO_ACTIVE_ATTENDANCE_LOCATION = "NO_ACTIVE_ATTENDANCE_LOCATION"

    # --- GPS ---
    GPS_INVALID = "GPS_INVALID"
    #: The reported accuracy *radius* is too large to be useful. The spec's
    #: name reads oddly next to a numeric comparison of `accuracy > max`, but
    #: it is kept verbatim so the API contract matches the specification.
    GPS_ACCURACY_TOO_LOW = "GPS_ACCURACY_TOO_LOW"
    OUTSIDE_GEOFENCE = "OUTSIDE_GEOFENCE"

    # --- QR ---
    QR_NOT_FOUND = "QR_NOT_FOUND"
    QR_EXPIRED = "QR_EXPIRED"
    QR_ALREADY_USED = "QR_ALREADY_USED"
    QR_REVOKED = "QR_REVOKED"
    QR_NONCE_MISMATCH = "QR_NONCE_MISMATCH"
    #: Internal only - a challenge belonging to a different tenant.
    QR_TENANT_MISMATCH = "QR_TENANT_MISMATCH"
    #: Internal only - a challenge bound to a different attendance location.
    QR_LOCATION_MISMATCH = "QR_LOCATION_MISMATCH"


#: Reasons that must not be reported verbatim to a client.
#:
#: Telling a caller "that challenge belongs to another tenant" confirms the id
#: exists somewhere, which is a cross-tenant existence oracle. Both mismatches
#: therefore surface as an indistinguishable ``QR_NOT_FOUND`` - the same
#: "missing or not yours" collapse used by ``app.db.tenant_scope``. The precise
#: reason is still recorded in the audit log, where it is a genuine signal that
#: somebody is probing across tenants.
CLIENT_SAFE_REASON: Final[dict[FailureReason, FailureReason]] = {
    FailureReason.QR_TENANT_MISMATCH: FailureReason.QR_NOT_FOUND,
    FailureReason.QR_LOCATION_MISMATCH: FailureReason.QR_NOT_FOUND,
}


def to_client_reason(reason: FailureReason) -> FailureReason:
    """Collapse internal-only reasons to their client-safe equivalent."""
    return CLIENT_SAFE_REASON.get(reason, reason)


@dataclass(frozen=True, slots=True)
class GPSResult:
    """Server-computed GPS verification result.

    Every field here is calculated by the server. ``distance_meters`` in
    particular is never accepted from a client - see
    :func:`app.services.presence.gps.verify_gps`.
    """

    verified: bool
    #: Great-circle distance to the attendance location. ``None`` only when the
    #: coordinates were invalid, so no distance could be computed.
    distance_meters: float | None
    #: The accuracy the device reported, echoed back for transparency.
    accuracy_meters: float
    reason: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class QRResult:
    """QR challenge verification result."""

    verified: bool
    challenge_id: uuid.UUID | None = None
    reason: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class PresenceDecision:
    """The combined presence decision.

    ``gps`` and ``qr`` are always populated so a caller can see which signal
    failed, even when the other was fine.
    """

    status: PresenceStatus
    gps: GPSResult
    qr: QRResult
    reason: FailureReason | None = None

    @property
    def verified(self) -> bool:
        return self.status is PresenceStatus.PRESENCE_VERIFIED

    def to_verification_metadata(self) -> dict[str, Any]:
        """Render this decision as ``attendance_events.verification_metadata``.

        Phase 3 never writes an attendance event - this exists so Phase 4 can
        persist the decision without reshaping it, and so the JSONB layout is
        fixed by one function rather than restated at each call site. The shape
        deliberately matches the structure documented for that column:

            {"gps": {"verified": …, "distance_meters": …, "accuracy_meters": …},
             "qr":  {"verified": …, "challenge_id": …}}
        """
        metadata: dict[str, Any] = {
            "gps": {
                "verified": self.gps.verified,
                "distance_meters": self.gps.distance_meters,
                "accuracy_meters": self.gps.accuracy_meters,
            },
            "qr": {
                "verified": self.qr.verified,
                "challenge_id": (
                    str(self.qr.challenge_id) if self.qr.challenge_id else None
                ),
            },
        }
        if self.reason is not None:
            metadata["failure_reason"] = self.reason.value
        return metadata
