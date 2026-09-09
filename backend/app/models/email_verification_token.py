"""EmailVerificationToken model - proves an onboarding admin controls the
email address they signed up with, before their account can be used.

Same shape as ``RefreshToken`` on purpose: only a hash of the token is ever
persisted, and both foreign keys use ``ON DELETE CASCADE`` - this is
authentication-adjacent ephemeral state with no record-keeping value of its
own, not something worth keeping once the tenant or user it belongs to is
gone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class EmailVerificationToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One issued email-verification link, identified by its token's hash.

    Usable only while ``consumed_at IS NULL`` and ``expires_at > now()``.
    Consuming sets ``consumed_at`` rather than deleting the row, so a
    replayed verification link is recognisably already-used instead of
    merely absent - the same reasoning ``RefreshToken.revoked_at`` uses.
    """

    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("ix_email_verification_tokens_user_id", "user_id"),
        Index("ix_email_verification_tokens_expires_at", "expires_at"),
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
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ------------------------------------------------------
    user: Mapped[User] = relationship()
    tenant: Mapped[Tenant] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately omits token_hash.
        return (
            f"<EmailVerificationToken id={self.id!s} user_id={self.user_id!s} "
            f"consumed={self.consumed_at is not None}>"
        )
