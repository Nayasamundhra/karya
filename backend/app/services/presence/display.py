"""Display-token lifecycle: create, list, revoke.

A display token is a kiosk credential, not a user session - see
`app.models.display_token` and `app.api.display_deps` for the full
reasoning. This module owns everything that touches the table; route
handlers and other services never construct or hash a token directly.

Creation and revocation are both audited (PRD-listed security-sensitive
actions), the same "audit row added to the caller's transaction" pattern
`app.services.users.service` uses - never the raw token itself, only the
label and the row's id.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tokens import generate_opaque_token, hash_opaque_token
from app.models.attendance_location import (
    LOCATION_STATUS_ACTIVE,
    AttendanceLocation,
)
from app.models.audit_log import AuditLog
from app.models.display_token import DisplayToken

ACTION_DISPLAY_TOKEN_CREATED: Final[str] = "DISPLAY_TOKEN_CREATED"
ACTION_DISPLAY_TOKEN_REVOKED: Final[str] = "DISPLAY_TOKEN_REVOKED"


class NoActiveAttendanceLocationError(Exception):
    """The tenant has no ACTIVE attendance location to bind a display to."""


def create_display_token(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    label: str,
) -> tuple[DisplayToken, str]:
    """Mint a new display token for the tenant's active location.

    Returns the persisted row and the raw token - the only time the raw
    value exists outside the caller's response body. The row is flushed (so
    it has an id) but the caller owns the commit.

    Raises:
        NoActiveAttendanceLocationError: if the tenant has no active location
            yet - a display exists to scan people into a place, so one must
            be configured first (see `app.services.tenant.service`).
    """
    location = session.scalar(
        select(AttendanceLocation).where(
            AttendanceLocation.tenant_id == tenant_id,
            AttendanceLocation.status == LOCATION_STATUS_ACTIVE,
        )
    )
    if location is None:
        raise NoActiveAttendanceLocationError

    raw_token = generate_opaque_token()
    record = DisplayToken(
        tenant_id=tenant_id,
        location_id=location.id,
        created_by_user_id=created_by_user_id,
        label=label,
        token_hash=hash_opaque_token(raw_token),
    )
    session.add(record)
    session.flush()

    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=created_by_user_id,
            action=ACTION_DISPLAY_TOKEN_CREATED,
            target_type=DisplayToken.__name__,
            target_id=record.id,
            log_metadata={"label": label},
        )
    )
    return record, raw_token


def list_display_tokens(session: Session, *, tenant_id: uuid.UUID) -> list[DisplayToken]:
    """Every display token issued for this tenant, newest first."""
    return list(
        session.scalars(
            select(DisplayToken)
            .where(DisplayToken.tenant_id == tenant_id)
            .order_by(DisplayToken.created_at.desc())
        )
    )


def revoke_display_token(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    display_token_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> DisplayToken | None:
    """Revoke one of the tenant's own display tokens.

    Tenant-scoped by construction, so one tenant can never revoke another's
    kiosk. Returns the row if it was found (whether or not it was already
    revoked - revoking twice is not an error), or ``None`` if no such token
    belongs to this tenant, which the route turns into a 404. An audit row is
    only written the first time - revoking an already-revoked token is a
    no-op, not a second event.

    ``actor_user_id`` is ``None`` for a kiosk's own self-revoke (see
    `app.api.v1.display.revoke_self` - resetting a physical display is not a
    person acting, the same "not a person" case
    `app.services.presence.service.issue_qr_challenge` already handles for
    display-issued QR challenges; `audit_logs.actor_user_id` is nullable for
    exactly this.
    """
    record = session.scalar(
        select(DisplayToken).where(
            DisplayToken.id == display_token_id, DisplayToken.tenant_id == tenant_id
        )
    )
    if record is None:
        return None
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action=ACTION_DISPLAY_TOKEN_REVOKED,
                target_type=DisplayToken.__name__,
                target_id=record.id,
                log_metadata={"label": record.label},
            )
        )
    return record
