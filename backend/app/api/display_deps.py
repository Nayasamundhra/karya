"""Authentication for the office-display kiosk endpoint only.

A display token identifies a physical screen, not a person. It is
deliberately a *separate* dependency from `app.api.deps.get_current_user` -
never merged, never accepted on any other route - so there is no path by
which a leaked display token (sitting on a shared, unattended device) could
be mistaken for, or escalated into, a real user's bearer token. It grants
exactly one capability: minting a QR challenge for its own tenant's location.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import update

from app.api.deps import DbSession
from app.core.tokens import hash_opaque_token
from app.models.display_token import DisplayToken

#: `auto_error=False` so a missing/malformed header reaches our own handler
#: and gets the same generic 401 as an unrecognised or revoked token.
_display_bearer_scheme = HTTPBearer(
    auto_error=False, description="Display token (kiosk credential)"
)
DisplayBearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_display_bearer_scheme)
]


@dataclass(frozen=True, slots=True)
class DisplayContext:
    """The kiosk identity resolved from a display token. Not a `User`."""

    display_token_id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID


def _unauthorized() -> HTTPException:
    """The one 401 used for every display-auth failure - identical for a
    missing header, an unrecognised token and a revoked one, so a caller
    cannot distinguish "wrong secret" from "this kiosk was decommissioned".
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_display(
    session: DbSession, credentials: DisplayBearerCredentials = None
) -> DisplayContext:
    """Resolve and validate a kiosk's display token, bumping its heartbeat.

    The lookup and the `last_used_at` bump happen in one `UPDATE ...
    RETURNING` so an unauthenticated caller can never cause a write (the
    `WHERE` excludes revoked tokens, so a rejected attempt touches no row),
    and so a revoked-in-another-request race can't leave a stale heartbeat.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    token_hash = hash_opaque_token(credentials.credentials)
    row = session.execute(
        update(DisplayToken)
        .where(
            DisplayToken.token_hash == token_hash,
            DisplayToken.revoked_at.is_(None),
        )
        .values(last_used_at=datetime.now(UTC))
        .returning(
            DisplayToken.id, DisplayToken.tenant_id, DisplayToken.location_id
        )
        .execution_options(synchronize_session=False)
    ).one_or_none()

    if row is None:
        raise _unauthorized()

    display_token_id, tenant_id, location_id = row
    return DisplayContext(
        display_token_id=display_token_id,
        tenant_id=tenant_id,
        location_id=location_id,
    )


CurrentDisplay = Annotated[DisplayContext, Depends(get_current_display)]
