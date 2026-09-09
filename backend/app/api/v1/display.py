"""Office-display (kiosk) token management routes.

TENANT_ADMIN/MANAGER only - the same `QR_ISSUER_ROLES` split that already
governs who may mint a QR challenge by hand, since minting a display token
is the same privilege at one remove: whoever gets one can point any browser
at the QR endpoint indefinitely, unattended.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, require_roles
from app.api.display_deps import CurrentDisplay
from app.api.limits import (
    ADMIN_WRITE_RATE_LIMIT,
    DISPLAY_SELF_REVOKE_RATE_LIMIT,
    RATE_LIMITED_RESPONSE,
)
from app.api.v1.presence import QR_ISSUER_ROLES
from app.models.user import User
from app.schemas.display import (
    DisplayTokenCreateRequest,
    DisplayTokenCreateResponse,
    DisplayTokenListResponse,
    DisplayTokenResponse,
)
from app.services.presence import display as display_service
from app.services.presence.display import NoActiveAttendanceLocationError

router = APIRouter(prefix="/tenant/display-tokens", tags=["display"])

#: Separate from `router` above: this one route is authenticated by the
#: kiosk's own display token (`CurrentDisplay`), never a user's bearer token,
#: so it cannot share a prefix that implies tenant-admin auth.
self_router = APIRouter(prefix="/display", tags=["display"])

DisplayTokenIssuer = Annotated[User, Depends(require_roles(*QR_ISSUER_ROLES))]

_NO_LOCATION_DETAIL = "Set up your attendance location before creating a display"


@router.post(
    "",
    response_model=DisplayTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a credential for one office-display kiosk",
    dependencies=[ADMIN_WRITE_RATE_LIMIT],
    responses={
        403: {"description": "Insufficient permissions"},
        409: {"description": _NO_LOCATION_DETAIL},
        **RATE_LIMITED_RESPONSE,
    },
)
def create_display_token(
    payload: DisplayTokenCreateRequest,
    session: DbSession,
    current_user: DisplayTokenIssuer,
) -> DisplayTokenCreateResponse:
    """Mint a new kiosk credential. The raw token is returned exactly once.

    Store it in the kiosk's browser immediately - there is no way to
    retrieve it again, only to revoke it and mint a replacement.
    """
    try:
        record, raw_token = display_service.create_display_token(
            session,
            tenant_id=current_user.tenant_id,
            created_by_user_id=current_user.id,
            label=payload.label,
        )
    except NoActiveAttendanceLocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_NO_LOCATION_DETAIL
        ) from exc

    session.commit()
    return DisplayTokenCreateResponse(
        id=record.id, label=record.label, token=raw_token, created_at=record.created_at
    )


@router.get(
    "",
    response_model=DisplayTokenListResponse,
    summary="List this tenant's office-display kiosks",
)
def list_display_tokens(
    session: DbSession, current_user: DisplayTokenIssuer
) -> DisplayTokenListResponse:
    """Never includes a raw token - only what was true at creation time plus
    each kiosk's revocation/heartbeat state, enough to decide which to revoke.
    """
    records = display_service.list_display_tokens(
        session, tenant_id=current_user.tenant_id
    )
    return DisplayTokenListResponse(
        items=[DisplayTokenResponse.model_validate(record) for record in records]
    )


@router.post(
    "/{display_token_id}/revoke",
    response_model=DisplayTokenResponse,
    summary="Revoke one office-display kiosk's credential",
    dependencies=[ADMIN_WRITE_RATE_LIMIT],
    responses={404: {"description": "No such display token"}, **RATE_LIMITED_RESPONSE},
)
def revoke_display_token(
    display_token_id: uuid.UUID, session: DbSession, current_user: DisplayTokenIssuer
) -> DisplayTokenResponse:
    """Immediately and permanently disable one kiosk's credential.

    404, not 403, for a display token belonging to another tenant - the same
    "cross-tenant lookups don't exist" posture every other admin route uses.
    """
    record = display_service.revoke_display_token(
        session,
        tenant_id=current_user.tenant_id,
        display_token_id=display_token_id,
        actor_user_id=current_user.id,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such display token"
        )

    session.commit()
    return DisplayTokenResponse.model_validate(record)


@self_router.post(
    "/revoke-self",
    response_model=DisplayTokenResponse,
    summary="A kiosk revokes its own credential",
    dependencies=[DISPLAY_SELF_REVOKE_RATE_LIMIT],
    responses={**RATE_LIMITED_RESPONSE},
)
def revoke_self(session: DbSession, display: CurrentDisplay) -> DisplayTokenResponse:
    """Let a kiosk disable itself - the "Reset this display" control.

    Deliberately narrow: a display token can revoke only the one row its own
    token identifies (`display.display_token_id`, derived from the token
    itself, never a request parameter - the same "identity is derived, not
    accepted" posture every tenant-scoped route already uses), so a leaked
    display token gains no capability beyond killing itself. There is no
    "un-revoke" - a reset kiosk needs a freshly minted token from an admin,
    same as any other revoked display.
    """
    record = display_service.revoke_display_token(
        session,
        tenant_id=display.tenant_id,
        display_token_id=display.display_token_id,
        actor_user_id=None,
    )
    assert record is not None  # the token that just authenticated this request
    session.commit()
    return DisplayTokenResponse.model_validate(record)
