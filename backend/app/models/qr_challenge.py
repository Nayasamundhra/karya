"""QRChallenge model - a short-lived, one-time-use QR presence nonce.

Only the persistence shape is defined here. QR generation, rotation and
validation are later phases.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendance_location import AttendanceLocation
    from app.models.tenant import Tenant


class QRChallengeStatus(enum.StrEnum):
    """Lifecycle of a QR challenge."""

    ACTIVE = "ACTIVE"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class QRChallenge(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single-use nonce bound to a tenant and its attendance location.

    ``nonce`` is globally unique so a value can never be replayed across
    tenants. Because QR challenges are disposable, both foreign keys use
    ``ON DELETE CASCADE`` - unlike attendance and audit data, losing them
    carries no record-keeping risk.
    """

    __tablename__ = "qr_challenges"
    __table_args__ = (
        # An index on `nonce` is redundant: the UNIQUE constraint below is
        # already backed by a unique index used for lookups.
        Index("ix_qr_challenges_tenant_id", "tenant_id"),
        Index("ix_qr_challenges_expires_at", "expires_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("attendance_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nonce: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=QRChallengeStatus.ACTIVE,
        server_default=text(f"'{QRChallengeStatus.ACTIVE.value}'"),
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship(back_populates="qr_challenges")
    location: Mapped[AttendanceLocation] = relationship(back_populates="qr_challenges")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<QRChallenge id={self.id!s} tenant_id={self.tenant_id!s} status={self.status!r}>"
