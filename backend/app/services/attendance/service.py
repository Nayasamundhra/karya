"""Attendance lifecycle: check-in and check-out.

Phase 3 answers *"is Rahul physically present?"*. This module answers *"given
that, should Karya record an attendance event?"* - and it is the only place that
writes to ``attendance_events``.

Two rules shape everything here:

**Presence is verified as part of the action, never taken on trust.** The client
cannot call ``/presence/verify`` and then tell us it passed. Every check-in and
check-out re-runs the real verification through
:func:`app.services.presence.service.verify_presence`, so the two entry points
cannot drift apart in their security behaviour. No GPS or QR logic is restated
here.

**One transaction covers state check, QR consumption and event creation.** The
caller commits once at the end. If anything raises in between, the session is
never committed and PostgreSQL discards the lot - so the database can never hold
a consumed QR challenge with no attendance event to show for it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.attendance_event import (
    AttendanceEvent,
    AttendanceEventType,
    VerificationStatus,
)
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.attendance.results import (
    STATE_AFTER_EVENT,
    STATE_REQUIRED_FOR_EVENT,
    AttendanceFailureReason,
    AttendanceOutcome,
    AttendanceState,
)
from app.services.presence import service as presence_service
from app.services.presence.results import PresenceDecision, to_client_reason

#: Audit actions written by this module.
ACTION_CHECK_IN = "ATTENDANCE_CHECK_IN"
ACTION_CHECK_OUT = "ATTENDANCE_CHECK_OUT"
ACTION_CHECK_IN_FAILED = "ATTENDANCE_CHECK_IN_FAILED"
ACTION_CHECK_OUT_FAILED = "ATTENDANCE_CHECK_OUT_FAILED"

_SUCCESS_ACTION = {
    AttendanceEventType.CHECK_IN: ACTION_CHECK_IN,
    AttendanceEventType.CHECK_OUT: ACTION_CHECK_OUT,
}
_FAILURE_ACTION = {
    AttendanceEventType.CHECK_IN: ACTION_CHECK_IN_FAILED,
    AttendanceEventType.CHECK_OUT: ACTION_CHECK_OUT_FAILED,
}

#: Reason returned when the user is in the wrong state for the action.
_WRONG_STATE_REASON = {
    AttendanceEventType.CHECK_IN: AttendanceFailureReason.ALREADY_CHECKED_IN,
    AttendanceEventType.CHECK_OUT: AttendanceFailureReason.NOT_CHECKED_IN,
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def get_latest_event(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> AttendanceEvent | None:
    """Return the user's most recent attendance event, or ``None``.

    Scoped by ``tenant_id`` as well as ``user_id`` - both come from the
    authenticated user, and the pair matches the Phase 1 composite index
    ``(tenant_id, user_id, event_timestamp)``.

    ``created_at`` breaks a tie in the (practically unreachable) case of two
    events sharing an ``event_timestamp``; per-user serialisation via
    :func:`_lock_user` means two attendance transactions for one user cannot
    overlap in the first place.
    """
    return session.scalar(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.tenant_id == tenant_id,
            AttendanceEvent.user_id == user_id,
        )
        .order_by(
            AttendanceEvent.event_timestamp.desc(),
            AttendanceEvent.created_at.desc(),
        )
        .limit(1)
    )


def get_current_state(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> AttendanceState:
    """Derive the user's attendance state from their latest event."""
    latest = get_latest_event(session, tenant_id=tenant_id, user_id=user_id)
    if latest is None:
        return AttendanceState.NOT_CHECKED_IN
    return STATE_AFTER_EVENT.get(
        AttendanceEventType(latest.event_type), AttendanceState.NOT_CHECKED_IN
    )


def _lock_user(
    session: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Take a row lock on the user for the rest of the transaction.

    This is what makes "read the state, then decide" safe. Without it two
    concurrent check-ins both read ``NOT_CHECKED_IN`` and both insert, producing
    ``CHECK_IN, CHECK_IN`` - the state machine broken by a race rather than by
    bad logic.

    ``SELECT ... FOR UPDATE`` serialises every attendance operation for one
    user: the second transaction blocks here until the first commits, and only
    then reads the state - by which point it sees the newly committed event and
    refuses. Different users lock different rows, so unrelated staff never
    contend.

    Locking the *user* row rather than the attendance rows is deliberate: at
    check-in time there may be no attendance rows to lock, and a gap lock is not
    something PostgreSQL offers under READ COMMITTED. The user row always
    exists, so it is a reliable mutex keyed by exactly the right thing.

    Lock order across the transaction is always user → QR challenge, so two
    transactions can never hold one another's next lock and deadlock.

    Returns whether the user exists within the tenant.
    """
    locked = session.execute(
        select(User.id)
        .where(User.id == user_id, User.tenant_id == tenant_id)
        .with_for_update()
    ).scalar_one_or_none()
    return locked is not None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _build_metadata(
    decision: PresenceDecision | None, *, state: AttendanceState
) -> dict[str, Any]:
    """Assemble the evidence recorded against an attendance event.

    Built from the presence decision rather than restated, so the JSONB layout
    stays defined in one place. Carries ``challenge_id`` but never the nonce:
    the id is enough to correlate an event with the challenge that authorised
    it, whereas the nonce is the secret the challenge protects.
    """
    metadata: dict[str, Any] = {"attendance_state": state.value}
    if decision is None:
        return metadata

    metadata.update(decision.to_verification_metadata())
    metadata["presence"] = {"verified": decision.verified}
    return metadata


def _record_audit(
    session: Session,
    *,
    action: str,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    target_id: uuid.UUID | None,
    metadata: dict[str, Any],
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=AttendanceEvent.__name__,
            target_id=target_id,
            log_metadata=metadata,
        )
    )


# ---------------------------------------------------------------------------
# The lifecycle
# ---------------------------------------------------------------------------


def record_attendance(
    session: Session,
    *,
    event_type: AttendanceEventType,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    latitude: float,
    longitude: float,
    accuracy_meters: float,
    challenge_id: uuid.UUID,
    nonce: str,
    config: Settings | None = None,
) -> AttendanceOutcome:
    """Record a check-in or check-out, if the user is present and eligible.

    ``tenant_id`` and ``user_id`` must come from the authenticated user; nothing
    in the request body can reach them.

    Order of operations, and why:

    1. **Lock the user row** - serialises this user's attendance operations.
    2. **Derive and validate state** - a duplicate check-in is refused *before*
       any evidence is examined, so it cannot consume the office's current QR
       challenge. The same reasoning Phase 3 applies to GPS failures.
    3. **Verify presence** - GPS, then QR, then an atomic consume, all inside
       the Phase 3 service.
    4. **Insert the event** - only once presence has actually passed.

    The caller owns the commit. Every write above lands in one transaction, so a
    failure anywhere leaves neither a consumed challenge nor an orphaned event.
    """
    config = config or settings

    if not _lock_user(session, tenant_id=tenant_id, user_id=user_id):
        # The authentication dependency already proved this user exists and is
        # active; reaching here means the row vanished mid-request.
        return AttendanceOutcome(
            success=False,
            event_type=event_type,
            state=AttendanceState.NOT_CHECKED_IN,
            reason=_WRONG_STATE_REASON[event_type],
        )

    state = get_current_state(session, tenant_id=tenant_id, user_id=user_id)

    if state is not STATE_REQUIRED_FOR_EVENT[event_type]:
        reason = _WRONG_STATE_REASON[event_type]
        _record_audit(
            session,
            action=_FAILURE_ACTION[event_type],
            tenant_id=tenant_id,
            actor_user_id=user_id,
            target_id=None,
            metadata={
                "failure_reason": reason.value,
                "attendance_state": state.value,
                "attempted_event_type": event_type.value,
            },
        )
        return AttendanceOutcome(
            success=False, event_type=event_type, state=state, reason=reason
        )

    decision = presence_service.verify_presence(
        session,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        challenge_id=challenge_id,
        nonce=nonce,
        config=config,
        # This module writes one richer audit row covering the whole attempt.
        audit_failures=False,
    )

    if not decision.verified:
        assert decision.reason is not None
        reason = to_client_reason(decision.reason)
        metadata = _build_metadata(decision, state=state)
        # The audit keeps the *internal* reason (e.g. QR_TENANT_MISMATCH) even
        # though the response collapses it - a cross-tenant probe should be
        # visible to whoever reads the trail.
        metadata["failure_reason"] = decision.reason.value
        metadata["attempted_event_type"] = event_type.value
        _record_audit(
            session,
            action=_FAILURE_ACTION[event_type],
            tenant_id=tenant_id,
            actor_user_id=user_id,
            target_id=decision.qr.challenge_id,
            metadata=metadata,
        )
        # State is unchanged: no event was written and the QR was not consumed.
        return AttendanceOutcome(
            success=False,
            event_type=event_type,
            state=state,
            reason=reason,
            presence=decision,
        )

    new_state = STATE_AFTER_EVENT[event_type]
    event = AttendanceEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type.value,
        # event_timestamp is deliberately omitted so PostgreSQL's now() fills
        # it. The device clock never reaches this column.
        latitude=latitude,
        longitude=longitude,
        gps_accuracy_meters=accuracy_meters,
        verification_status=VerificationStatus.VERIFIED.value,
        verification_metadata=_build_metadata(decision, state=new_state),
    )
    session.add(event)
    session.flush()
    # Fetch the server-generated timestamp so the client can display the time
    # actually recorded rather than guessing.
    session.refresh(event, ["event_timestamp"])

    _record_audit(
        session,
        action=_SUCCESS_ACTION[event_type],
        tenant_id=tenant_id,
        actor_user_id=user_id,
        target_id=event.id,
        metadata={
            "attendance_event_id": str(event.id),
            "event_type": event_type.value,
            "attendance_state": new_state.value,
            "challenge_id": (
                str(decision.qr.challenge_id) if decision.qr.challenge_id else None
            ),
            "distance_meters": decision.gps.distance_meters,
            "accuracy_meters": decision.gps.accuracy_meters,
        },
    )

    return AttendanceOutcome(
        success=True,
        event_type=event_type,
        state=new_state,
        event_id=event.id,
        event_timestamp=event.event_timestamp,
        presence=decision,
    )


def check_in(session: Session, **kwargs: Any) -> AttendanceOutcome:
    """Record a CHECK_IN. Requires the user to be NOT_CHECKED_IN."""
    return record_attendance(
        session, event_type=AttendanceEventType.CHECK_IN, **kwargs
    )


def check_out(session: Session, **kwargs: Any) -> AttendanceOutcome:
    """Record a CHECK_OUT. Requires the user to be CHECKED_IN."""
    return record_attendance(
        session, event_type=AttendanceEventType.CHECK_OUT, **kwargs
    )
