"""DisplayToken model - a credential for one physical office-display kiosk.

Unlike a refresh token, this is *not* a user session: it identifies a shared
screen, not a person, and it is meant to persist indefinitely once issued (a
tenant admin lists and labels their kiosks, the way they would API keys).
Both foreign keys are therefore ``ON DELETE RESTRICT``, matching
``attendance_locations`` - a tenant with a live display cannot be deleted by
accident. ``created_by_user_id`` alone is ``SET NULL``, matching
``audit_logs.actor_user_id``: the record of *which kiosk exists* must outlive
whichever admin happened to set it up.

Only a hash of the token is ever persisted - see
``app.services.presence.display`` - and it grants exactly one capability
(minting a QR challenge for its own tenant's location) via a dedicated
dependency (`app.api.display_deps`) that is never confused with a user's
bearer token.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendance_location import AttendanceLocation
    from app.models.tenant import Tenant
    from app.models.user import User


class DisplayToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One issued kiosk credential, identified by its token's hash."""

    __tablename__ = "display_tokens"
    __table_args__ = (
        Index("ix_display_tokens_tenant_id", "tenant_id"),
        Index("ix_display_tokens_location_id", "location_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("attendance_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: A human label the admin chose, e.g. "Reception tablet" - shown back to
    #: them when listing/revoking, never used for anything security-relevant.
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    #: SHA-256 hex digest of the raw token - never the raw token itself.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship()
    location: Mapped[AttendanceLocation] = relationship()
    created_by: Mapped[User | None] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately omits token_hash.
        return (
            f"<DisplayToken id={self.id!s} tenant_id={self.tenant_id!s} "
            f"label={self.label!r} revoked={self.revoked_at is not None}>"
        )
