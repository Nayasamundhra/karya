"""AttendanceEvent model - the source of truth for attendance.

Check-in/check-out business logic and the attendance API are later phases.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Double, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class AttendanceEventType(enum.StrEnum):
    """Kind of attendance event."""

    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class VerificationStatus(enum.StrEnum):
    """Outcome of presence verification for an event."""

    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class AttendanceEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable record of a staff check-in or check-out.

    ``event_timestamp`` is **server-generated** (``now()``). The client is
    never trusted to supply the authoritative attendance time; any
    client-reported time belongs in ``verification_metadata`` as a signal, not
    here.

    ``latitude`` / ``longitude`` / ``gps_accuracy_meters`` are nullable: they
    record what the device reported, which may be unavailable.

    Both foreign keys are ``ON DELETE RESTRICT`` - attendance records are
    business-critical and must never be removed as a side effect of deleting a
    user or a tenant.
    """

    __tablename__ = "attendance_events"
    __table_args__ = (
        Index("ix_attendance_events_tenant_id", "tenant_id"),
        Index("ix_attendance_events_user_id", "user_id"),
        Index("ix_attendance_events_event_timestamp", "event_timestamp"),
        # Primary read pattern: one user's attendance history within a tenant,
        # ordered/filtered by time.
        Index(
            "ix_attendance_events_tenant_id_user_id_event_timestamp",
            "tenant_id",
            "user_id",
            "event_timestamp",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    latitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Double, nullable=True)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(Double, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Deliberately schema-less: future verification signals (Wi-Fi, device
    # integrity, risk score, ...) must not require a migration.
    verification_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship(back_populates="attendance_events")
    user: Mapped[User] = relationship(back_populates="attendance_events")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<AttendanceEvent id={self.id!s} user_id={self.user_id!s} "
            f"type={self.event_type!r} at={self.event_timestamp!s}>"
        )
