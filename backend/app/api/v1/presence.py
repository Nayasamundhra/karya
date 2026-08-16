"""Presence verification routes.

Thin by design: authenticate (via the Phase 2 dependencies), delegate to
:mod:`app.services.presence.service`, commit. No GPS arithmetic, no QR SQL and
no tenant authorization logic is restated here.

Tenant context is taken from ``current_user.tenant_id`` in both routes; neither
accepts a tenant or user identifier from the request.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models.user import User, UserRole
from app.schemas.presence import (
    PresenceVerificationRequest,
    PresenceVerificationResponse,
    QRChallengeResponse,
)
from app.services.presence import service as presence_service
from app.services.presence.service import NoActiveAttendanceLocationError

router = APIRouter(prefix="/presence", tags=["presence"])

#: Roles permitted to mint an office QR challenge.
#:
#: STAFF is excluded on purpose: anyone who can generate a challenge can
#: generate one away from the office and redeem it themselves, which would
#: defeat the second presence signal entirely. Generating codes is an
#: administrative act tied to the physical display.
QR_ISSUER_ROLES = (UserRole.TENANT_ADMIN, UserRole.MANAGER)

QRIssuer = Annotated[User, Depends(require_roles(*QR_ISSUER_ROLES))]

_NO_LOCATION_DETAIL = "No active attendance location is configured"


@router.post(
    "/qr/challenge",
    response_model=QRChallengeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a short-lived QR challenge for the office display",
    responses={
        403: {"description": "Insufficient permissions"},
        409: {"description": _NO_LOCATION_DETAIL},
    },
)
def create_qr_challenge(
    session: DbSession, current_user: QRIssuer
) -> QRChallengeResponse:
    """Mint a new dynamic QR challenge for the caller's own tenant.

    The tenant and its attendance location are resolved from the authenticated
    user, so a caller cannot issue a challenge for anyone else's site. The
    challenge is single-use and expires after the configured TTL; the display is
    expected to re-request one shortly before it lapses.
    """
    try:
        challenge, ttl_seconds = presence_service.issue_qr_challenge(
            session,
            tenant_id=current_user.tenant_id,
            actor_user_id=current_user.id,
        )
    except NoActiveAttendanceLocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_NO_LOCATION_DETAIL
        ) from exc

    session.commit()
    return QRChallengeResponse(
        challenge_id=challenge.id,
        nonce=challenge.nonce,
        expires_at=challenge.expires_at,
        expires_in=ttl_seconds,
    )


@router.post(
    "/verify",
    response_model=PresenceVerificationResponse,
    summary="Verify physical presence from GPS and QR evidence",
    responses={401: {"description": "Not authenticated"}},
)
def verify_presence(
    payload: PresenceVerificationRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> PresenceVerificationResponse:
    """Evaluate GPS + QR evidence for the authenticated user.

    Open to any authenticated, active user of the tenant - STAFF included, since
    proving one's own presence is the normal staff action.

    A rejection is returned as **200 with ``verified: false``**, not a 4xx: the
    request was well-formed and processed, and the body carries a structured
    verdict per signal. HTTP error codes are reserved for requests that could
    not be processed at all (401 unauthenticated, 422 malformed evidence).

    The commit persists the audit row and, on success, the QR consumption.
    """
    decision = presence_service.verify_presence(
        session,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        challenge_id=payload.challenge_id,
        nonce=payload.nonce,
    )
    session.commit()
    return PresenceVerificationResponse.from_decision(decision)
