"""RefreshToken model - server-side record of an issued refresh token.

Only a **hash** of the token is ever persisted (see
``app.services.auth.refresh_tokens``). The raw token exists solely in the
response body sent to the client and is never written to the database or a log.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One issued refresh token, identified by the hash of its raw value.

    Unlike attendance and audit rows, a refresh token is *authentication state*
    with no record-keeping value, so both foreign keys use ``ON DELETE
    CASCADE``: removing a user or tenant should take their sessions with it
    rather than block the delete or leave orphaned credentials behind.

    A token is usable only while ``revoked_at IS NULL`` and
    ``expires_at > now()``. Rotation sets ``revoked_at`` on the old row rather
    than deleting it, so a replayed token is recognisably revoked instead of
    merely absent.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_tenant_id", "tenant_id"),
        # Supports periodic cleanup of expired rows.
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        # Active-session lookup for one user. Partial, so it stays small no
        # matter how many revoked rows accumulate.
        Index(
            "ix_refresh_tokens_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: SHA-256 hex digest of the raw token - never the raw token itself.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ------------------------------------------------------
    user: Mapped[User] = relationship(back_populates="refresh_tokens")
    tenant: Mapped[Tenant] = relationship(back_populates="refresh_tokens")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately omits token_hash.
        return (
            f"<RefreshToken id={self.id!s} user_id={self.user_id!s} "
            f"revoked={self.revoked_at is not None}>"
        )
