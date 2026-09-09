"""Presence verification: coordinates the GPS and QR signals into one decision.

Answers exactly one question - *"is this authenticated staff member physically
at their tenant's attendance location right now?"* - and nothing more. It
deliberately does **not** create an ``AttendanceEvent``: deciding what
attendance action verified presence should cause is Phase 4's job. Keeping the
two apart means presence can be re-evaluated, audited or refused without any
attendance side effect.

Every input that matters is derived server-side:

* the user comes from the validated bearer token (``current_user.id``),
* the tenant comes from that user's database row (``current_user.tenant_id``),
* the attendance location comes from a tenant-scoped query,
* the distance is computed by :mod:`app.services.presence.gps`,
* the QR verdict comes from :mod:`app.services.presence.qr`.

The request body contributes only raw evidence: coordinates, accuracy, a
challenge id and a nonce.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.attendance_location import (
    LOCATION_STATUS_ACTIVE,
    AttendanceLocation,
)
from app.models.audit_log import AuditLog
from app.models.qr_challenge import QRChallenge
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
ACTION_QR_CHALLENGE_CREATED = "QR_CHALLENGE_CREATED"
ACTION_PRESENCE_VERIFICATION_FAILED = "PRESENCE_VERIFICATION_FAILED"


class NoActiveAttendanceLocationError(Exception):
    """The tenant has no ACTIVE attendance location configured."""


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
    metadata: dict[str, Any],
) -> AuditLog:
    """Append an audit row. Never receives a nonce or any credential."""
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        action=action,
        target_type=QRChallenge.__name__,
        target_id=target_id,
        log_metadata=metadata,
    )
    session.add(entry)
    return entry


# ---------------------------------------------------------------------------
# QR challenge creation (office display)
# ---------------------------------------------------------------------------


def issue_qr_challenge(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    config: Settings | None = None,
) -> tuple[QRChallenge, int]:
    """Create a challenge for the tenant's active location and audit it.

    Returns the challenge and its TTL in seconds.

    ``actor_user_id`` is ``None`` when a kiosk's display token (rather than a
    signed-in MANAGER/TENANT_ADMIN) is the caller - see
    `app.api.display_deps`. A display token identifies a screen, not a
    person, and `audit_logs.actor_user_id` is nullable for exactly this case
    (the same way it already is for tenant-less platform actions).

    Raises:
        NoActiveAttendanceLocationError: if the tenant has no active location.
    """
    config = config or settings
    location = get_active_attendance_location(session, tenant_id=tenant_id)
    if location is None:
        raise NoActiveAttendanceLocationError

    challenge = qr_service.create_challenge(
        session, tenant_id=tenant_id, location_id=location.id, config=config
    )

    _record_audit(
        session,
        action=ACTION_QR_CHALLENGE_CREATED,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_id=challenge.id,
        metadata={
            # The nonce is deliberately absent. It is the secret the challenge
            # protects, and audit logs are widely readable; the challenge id is
            # enough to correlate creation with a later redemption.
            "challenge_id": str(challenge.id),
            "location_id": str(location.id),
            "expires_at": challenge.expires_at.isoformat(),
            "ttl_seconds": config.qr_challenge_ttl_seconds,
        },
    )
    return challenge, config.qr_challenge_ttl_seconds


# ---------------------------------------------------------------------------
# Presence verification
# ---------------------------------------------------------------------------


def _rejected(
    gps: GPSResult, qr: QRResult, reason: FailureReason
) -> PresenceDecision:
    return PresenceDecision(
        status=PresenceStatus.PRESENCE_REJECTED, gps=gps, qr=qr, reason=reason
    )


def verify_presence(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    latitude: float,
    longitude: float,
    accuracy_meters: float,
    challenge_id: uuid.UUID,
    nonce: str,
    config: Settings | None = None,
    audit_failures: bool = True,
) -> PresenceDecision:
    """Evaluate GPS + QR evidence and return the presence decision.

    Both signals are mandatory. Ordering matters and is chosen deliberately:

    1. resolve the tenant's active location,
    2. evaluate GPS,
    3. evaluate the QR challenge **read-only**,
    4. only if *both* passed, atomically consume the challenge.

    Consuming last is the point. If the QR were spent before the GPS check, a
    staff member standing 500 m away would destroy a perfectly good code that
    someone at the office still needed - and every failed attempt would burn the
    office's current QR, which is a trivial denial-of-service. So a rejected
    attempt leaves the challenge untouched and reusable by whoever is actually
    present.

    Consuming still has to be race-safe, which is why step 4 is a single
    conditional UPDATE rather than a write based on step 3's read. If this call
    loses that race the challenge is re-inspected to report the true reason
    (normally ``QR_ALREADY_USED``) instead of assuming success.

    Failed attempts are audited; the caller owns the commit. Pass
    ``audit_failures=False`` when the caller writes its own, richer audit row
    for the same user action - attendance does this, so one rejected check-in
    produces one audit entry rather than a presence row and an attendance row
    describing the same event.
    """
    config = config or settings

    location = get_active_attendance_location(session, tenant_id=tenant_id)
    if location is None:
        # No location means no geofence to test against, so no distance exists.
        decision = _rejected(
            GPSResult(
                verified=False,
                distance_meters=None,
                accuracy_meters=accuracy_meters,
                reason=FailureReason.NO_ACTIVE_ATTENDANCE_LOCATION,
            ),
            QRResult(verified=False, reason=FailureReason.NO_ACTIVE_ATTENDANCE_LOCATION),
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

    # The QR is evaluated even when GPS already failed, so the response can tell
    # the user everything that is wrong in one round trip rather than one
    # problem at a time. This is a read-only check - nothing is consumed.
    qr = qr_service.validate_challenge(
        session,
        challenge_id=challenge_id,
        nonce=nonce,
        tenant_id=tenant_id,
        location_id=location.id,
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

    if not qr_service.consume_challenge(
        session,
        challenge_id=challenge_id,
        nonce=nonce,
        tenant_id=tenant_id,
        location_id=location.id,
    ):
        # Another request claimed it between our check and our write, or it
        # lapsed in that instant. Re-read to report what actually happened.
        recheck = qr_service.validate_challenge(
            session,
            challenge_id=challenge_id,
            nonce=nonce,
            tenant_id=tenant_id,
            location_id=location.id,
        )
        reason = recheck.reason or FailureReason.QR_ALREADY_USED
        decision = _rejected(
            gps,
            QRResult(verified=False, challenge_id=qr.challenge_id, reason=reason),
            reason,
        )
        if audit_failures:
            _audit_failure(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                decision=decision,
            )
        return decision

    return PresenceDecision(
        status=PresenceStatus.PRESENCE_VERIFIED, gps=gps, qr=qr
    )


def _audit_failure(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    decision: PresenceDecision,
) -> None:
    """Audit a rejected presence attempt.

    Failures are logged, successes are not: a rejection is the security-relevant
    event (repeated ``QR_TENANT_MISMATCH`` from one user is somebody probing
    across tenants), whereas a success will be recorded by Phase 4 as an
    attendance event carrying this same metadata. Logging both would duplicate
    the record and bury the signal in noise.

    The stored reason is the *internal* one, which is the whole point - the audit
    trail distinguishes "no such challenge" from "another tenant's challenge"
    even though the API response cannot.
    """
    metadata = decision.to_verification_metadata()
    metadata["outcome"] = decision.status.value
    _record_audit(
        session,
        action=ACTION_PRESENCE_VERIFICATION_FAILED,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        target_id=decision.qr.challenge_id,
        metadata=metadata,
    )


def client_facing_reason(decision: PresenceDecision) -> FailureReason | None:
    """The decision's failure reason, with internal-only values collapsed."""
    if decision.reason is None:
        return None
    return to_client_reason(decision.reason)
