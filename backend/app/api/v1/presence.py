"""Presence verification routes.

Thin by design: authenticate (via the Phase 2 dependencies), delegate to
:mod:`app.services.presence.service`, commit. No GPS arithmetic and no QR
lookup logic is restated here.

Tenant context is taken from ``current_user.tenant_id``; the route never
accepts a tenant or user identifier from the request.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.limits import PRESENCE_RATE_LIMIT, RATE_LIMITED_RESPONSE
from app.schemas.presence import (
    PresenceVerificationRequest,
    PresenceVerificationResponse,
)
from app.services.presence import service as presence_service

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post(
    "/verify",
    response_model=PresenceVerificationResponse,
    summary="Verify physical presence from GPS and a static QR token",
    dependencies=[PRESENCE_RATE_LIMIT],
    responses={401: {"description": "Not authenticated"}, **RATE_LIMITED_RESPONSE},
)
def verify_presence(
    payload: PresenceVerificationRequest,
    session: DbSession,
    current_user: CurrentUser,
) -> PresenceVerificationResponse:
    """Evaluate GPS + QR evidence for the authenticated user.

    Open to any authenticated, active user of the tenant - STAFF included,
    since proving one's own presence is the normal staff action.

    A rejection is returned as **200 with ``verified: false``**, not a 4xx:
    the request was well-formed and processed, and the body carries a
    structured verdict per signal. HTTP error codes are reserved for
    requests that could not be processed at all (401 unauthenticated, 422
    malformed evidence).

    The commit persists the audit row written on a rejection; nothing is
    consumed on success - the QR token is static and reusable by design.
    """
    decision = presence_service.verify_presence(
        session,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        qr_token=payload.qr_token,
    )
    session.commit()
    return PresenceVerificationResponse.from_decision(decision)
