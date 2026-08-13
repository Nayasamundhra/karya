"""Refresh-token store operations.

Refresh tokens are **opaque random strings**, not JWTs, so they can be revoked
server-side. The raw value is returned to the client exactly once and never
persisted; the database holds only its SHA-256 digest.

Why SHA-256 rather than Argon2 here, when passwords use Argon2: a refresh token
is 256 bits of output from a CSPRNG, not a low-entropy human secret, so there is
no dictionary to slow an attacker down against - and a *deterministic* digest is
what allows the token to be looked up by a single indexed equality query. Argon2
would make lookup impossible without scanning every row.

This module deliberately contains no user/tenant validation; that belongs to
:mod:`app.services.auth.service`.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.refresh_token import RefreshToken
from app.models.user import User

#: Bytes of entropy per refresh token. 32 bytes = 256 bits, url-safe encoded to
#: roughly 43 characters.
REFRESH_TOKEN_BYTES: Final[int] = 32


@dataclass(frozen=True, slots=True)
class IssuedRefreshToken:
    """A freshly minted refresh token and its database row.

    ``raw_token`` is the only place the plaintext value exists; it must be put
    straight into the HTTP response and never logged or stored.
    """

    raw_token: str
    record: RefreshToken


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest used as the stored ``token_hash``."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    """Return a new cryptographically secure, URL-safe opaque token."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def issue_refresh_token(
    session: Session, *, user: User, config: Settings | None = None
) -> IssuedRefreshToken:
    """Create and persist a refresh token for ``user``.

    The row is added to ``session`` and flushed (so it has an ``id``), but the
    caller owns the commit.
    """
    config = config or settings
    raw_token = generate_raw_token()
    record = RefreshToken(
        user_id=user.id,
        # Denormalised from the user so tenant-scoped queries over sessions do
        # not need a join. It is copied from the DB user, never from a request.
        tenant_id=user.tenant_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC)
        + timedelta(days=config.refresh_token_expire_days),
    )
    session.add(record)
    session.flush()
    return IssuedRefreshToken(raw_token=raw_token, record=record)


def find_by_raw_token(session: Session, raw_token: str) -> RefreshToken | None:
    """Look up a token row by the hash of ``raw_token``, regardless of state."""
    return session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(raw_token)
        )
    )


def is_usable(record: RefreshToken, *, now: datetime | None = None) -> bool:
    """Whether ``record`` may still be exchanged: not revoked, not expired."""
    now = now or datetime.now(UTC)
    return record.revoked_at is None and record.expires_at > now


def find_usable_by_raw_token(session: Session, raw_token: str) -> RefreshToken | None:
    """Return the token row for ``raw_token`` only if it is still usable."""
    record = find_by_raw_token(session, raw_token)
    if record is None or not is_usable(record):
        return None
    return record


def revoke(record: RefreshToken, *, now: datetime | None = None) -> None:
    """Mark ``record`` revoked, leaving an already-revoked row untouched.

    Revoking rather than deleting means a replayed token is identifiable as
    revoked instead of merely missing.
    """
    if record.revoked_at is None:
        record.revoked_at = now or datetime.now(UTC)


def revoke_all_for_user(session: Session, *, user: User) -> int:
    """Revoke every active token for ``user``; returns how many were revoked.

    Not wired to an endpoint yet - it is what a future "log out everywhere" or
    forced-reauthentication flow will call.
    """
    now = datetime.now(UTC)
    records = session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    for record in records:
        revoke(record, now=now)
    return len(records)
