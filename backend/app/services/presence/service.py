"""Presence verification: coordinates the GPS and static-QR signals into one decision.

Answers exactly one question - *"is this authenticated staff member physically
at their tenant's attendance location right now?"* - and nothing more. It
deliberately does **not** create an ``AttendanceEvent``: deciding what
attendance action verified presence should cause is Phase 4's job. Keeping the
two apart means presence can be re-evaluated, audited or refused without any
attendance side effect.

Every input that matters is derived server-side:

* the user comes from the validated bearer token (``current_user.id``),
* the tenant comes from that user's database row (``current_user.tenant_id``),
* the attendance location comes from the scanned QR token, tenant-scoped,
* the distance is computed by :mod:`app.services.presence.gps`.

The request body contributes only raw evidence: coordinates, accuracy and a
QR token. GPS is the only signal that actually gates a decision now - the
static QR (see :mod:`app.services.presence.qr`) just tells the server which
location to test the coordinates against, and does not prove proximity to a
display the way the old rotating challenge did. That trade is deliberate; see
`backend/README.md`'s presence section for the reasoning and the residual
risk it leaves (GPS spoofing on a rooted/dev-mode device is not detected
here, and was never fully closed even under the old dynamic-QR model).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.attendance_location import (
    LOCATION_STATUS_ACTIVE,
    AttendanceLocation,
)
from app.models.audit_log import AuditLog
from app.services.presence import qr as qr_service
from app.services.presence.gps import verify_gps
from app.services.presence.results import (
    FailureReason,
    GPSResult,
    PresenceDecision,
    PresenceStatus,
    QRResult,
    to_client_reason,
)

#: Audit actions written by this module.
ACTION_PRESENCE_VERIFICATION_FAILED = "PRESENCE_VERIFICATION_FAILED"


# ---------------------------------------------------------------------------
# Attendance location
# ---------------------------------------------------------------------------


def get_active_attendance_location(
    session: Session, *, tenant_id: uuid.UUID
) -> AttendanceLocation | None:
    """Return the tenant's single ACTIVE attendance location, if any.

    Tenant-scoped by construction: ``tenant_id`` must come from the
    authenticated user, so this can never return another tenant's site. V1
    guarantees at most one row per tenant via ``UNIQUE(tenant_id)``.
    """
    return session.scalar(
        select(AttendanceLocation).where(
            AttendanceLocation.tenant_id == tenant_id,
            AttendanceLocation.status == LOCATION_STATUS_ACTIVE,
        )
    )


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _record_audit(
    session: Session,
    *,
    action: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    target_id: uuid.UUID | None,
    metadata: dict,
) -> AuditLog:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=AttendanceLocation.__name__,
        target_id=target_id,
        log_metadata=metadata,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------------
# Presence verification
# ---------------------------------------------------------------------------


def _rejected(
    gps: GPSResult, qr: QRResult, reason: FailureReason
) -> PresenceDecision:
    return PresenceDecision(
        status=PresenceStatus.PRESENCE_REJECTED, gps=gps, qr=qr, reason=reason
    )


def _resolve_qr(
    session: Session, *, tenant_id: uuid.UUID, qr_token: uuid.UUID
) -> QRResult:
    """Resolve a scanned token to this tenant's own location, or fail.

    A token that resolves to a real but different tenant's location is
    reported internally as ``QR_TENANT_MISMATCH`` (a genuine probing signal
    for the audit log) and collapsed to the client-safe ``QR_NOT_FOUND``
    before it ever reaches a response - the same "missing or not yours"
    posture used everywhere else tenant isolation matters.
    """
    location = qr_service.resolve_location_by_qr_token(session, qr_token=qr_token)
    if location is None:
        return QRResult(verified=False, reason=FailureReason.QR_NOT_FOUND)
    if location.tenant_id != tenant_id:
        return QRResult(
            verified=False,
            location_id=location.id,
            reason=FailureReason.QR_TENANT_MISMATCH,
        )
    return QRResult(verified=True, location_id=location.id)


def verify_presence(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    latitude: float,
    longitude: float,
    accuracy_meters: float,
    qr_token: uuid.UUID,
    config: Settings | None = None,
    audit_failures: bool = True,
) -> PresenceDecision:
    """Evaluate GPS + QR evidence and return the presence decision.

    The QR resolves which location to test the GPS reading against; GPS is
    the only signal that can actually reject a genuinely present person's
    attempt. Both are still reported so a caller can see which one is wrong
    ("no such QR" vs. "350 m away") in one round trip.

    Failed attempts are audited; the caller owns the commit.  Pass
    ``audit_failures=False`` when the caller writes its own, richer audit row
    for the same user action - attendance does this, so one rejected
    check-in produces one audit entry rather than a presence row and an
    attendance row describing the same event.
    """
    config = config or settings

    qr = _resolve_qr(session, tenant_id=tenant_id, qr_token=qr_token)

    location = get_active_attendance_location(session, tenant_id=tenant_id)
    if location is None:
        # No location means no geofence to test against, so no distance
        # exists - report this ahead of whatever the QR said, since it is
        # the more fundamental problem (the tenant is not even set up yet).
        decision = _rejected(
            GPSResult(
                verified=False,
                distance_meters=None,
                accuracy_meters=accuracy_meters,
                reason=FailureReason.NO_ACTIVE_ATTENDANCE_LOCATION,
            ),
            qr,
            FailureReason.NO_ACTIVE_ATTENDANCE_LOCATION,
        )
        if audit_failures:
            _audit_failure(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                decision=decision,
            )
        return decision

    gps = verify_gps(
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        location=location,
        config=config,
    )

    if not gps.verified or not qr.verified:
        # GPS failure is reported first: it is the signal the user can act on.
        reason = gps.reason or qr.reason
        assert reason is not None  # one of them failed, so a reason exists
        decision = _rejected(gps, qr, reason)
        if audit_failures:
            _audit_failure(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                decision=decision,
            )
        return decision

    return PresenceDecision(status=PresenceStatus.PRESENCE_VERIFIED, gps=gps, qr=qr)


def _audit_failure(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    decision: PresenceDecision,
) -> None:
    """Audit a rejected presence attempt.

    Failures are logged, successes are not: a rejection is the
    security-relevant event (repeated ``QR_TENANT_MISMATCH`` from one user is
    somebody probing across tenants), whereas a success will be recorded by
    Phase 4 as an attendance event carrying this same metadata. Logging both
    would duplicate the record and bury the signal in noise.

    The stored reason is the *internal* one, which is the whole point - the
    audit trail distinguishes "no such QR" from "another tenant's QR" even
    though the API response cannot.
    """
    metadata = decision.to_verification_metadata()
    metadata["outcome"] = decision.status.value
    _record_audit(
        session,
        action=ACTION_PRESENCE_VERIFICATION_FAILED,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_id=decision.qr.location_id,
        metadata=metadata,
    )


def client_facing_reason(decision: PresenceDecision) -> FailureReason | None:
    """The decision's failure reason, with internal-only values collapsed."""
    if decision.reason is None:
        return None
    return to_client_reason(decision.reason)
