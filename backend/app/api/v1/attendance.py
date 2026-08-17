"""Attendance routes: check-in and check-out.

Thin, like the rest of the API layer. Identity and tenant come from the Phase 2
dependency; the whole lifecycle lives in
:mod:`app.services.attendance.service`; presence is re-verified inside that
service on every call.

Both handlers commit exactly once, at the end. That single commit is the
transaction boundary covering the state check, the QR consumption and the
attendance row - so the three cannot be persisted separately.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.attendance import AttendanceActionRequest, AttendanceActionResponse
from app.services.attendance import service as attendance_service

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _record(
    session: DbSession,
    current_user: CurrentUser,
    payload: AttendanceActionRequest,
    action,
) -> AttendanceActionResponse:
    """Run one attendance action and commit.

    A refused attempt is committed too: it wrote an audit row and nothing else,
    and that row is the record that somebody tried. Only an unexpected exception
    skips the commit, in which case the session closes without one and
    PostgreSQL discards every write - including any QR consumption.
    """
    outcome = action(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        challenge_id=payload.challenge_id,
        nonce=payload.nonce,
    )
    session.commit()
    return AttendanceActionResponse.from_outcome(outcome)


@router.post(
    "/check-in",
    response_model=AttendanceActionResponse,
    summary="Check in, after verifying presence",
    responses={401: {"description": "Not authenticated"}},
)
def check_in(
    payload: AttendanceActionRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> AttendanceActionResponse:
    """Record a CHECK_IN for the authenticated user.

    Presence is verified here as part of the action - a prior call to
    ``/presence/verify`` neither helps nor is trusted. The user must currently
    be ``NOT_CHECKED_IN``; a duplicate attempt is refused with
    ``ALREADY_CHECKED_IN`` and, deliberately, without consuming the QR
    challenge.
    """
    return _record(session, current_user, payload, attendance_service.check_in)


@router.post(
    "/check-out",
    response_model=AttendanceActionResponse,
    summary="Check out, after verifying presence",
    responses={401: {"description": "Not authenticated"}},
)
def check_out(
    payload: AttendanceActionRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> AttendanceActionResponse:
    """Record a CHECK_OUT for the authenticated user.

    Requires a preceding CHECK_IN: without one the attempt is refused with
    ``NOT_CHECKED_IN``. Needs its own fresh QR challenge, since the one that
    authorised the check-in was consumed by it.
    """
    return _record(session, current_user, payload, attendance_service.check_out)
