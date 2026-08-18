"""AttendanceEvent model - the source of truth for attendance.

Check-in/check-out business logic and the attendance API are later phases.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Double, ForeignKey, Index, String, text
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

    ``event_timestamp`` is **server-generated** (``clock_timestamp()``). The
    client is never trusted to supply the authoritative attendance time; any
    client-reported time belongs in ``verification_metadata`` as a signal, not
    here. See the column for why it is not ``now()``.

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
        # Tenant-wide day queries (the team dashboard), which constrain tenant
        # and time but no single user. The composite above cannot serve those:
        # with `user_id` unconstrained in the middle it degrades to scanning
        # every index entry the tenant has ever accumulated - measured at 9,600
        # entries read to return 80 rows after only 120 days, and growing
        # without bound as history deepens. This index reads just the day.
        Index(
            "ix_attendance_events_tenant_id_event_timestamp",
            "tenant_id",
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
        # `clock_timestamp()`, NOT `now()`. `now()` is the *transaction start*
        # time, which is wrong for this column in a way that corrupts state:
        #
        #   1. Two check-ins race. Transaction B begins, then A begins, takes the
        #      user row lock and inserts a CHECK_IN stamped at A's start time.
        #   2. B was blocked on the lock the whole time. It wakes, correctly sees
        #      the CHECK_IN, and inserts a legitimate CHECK_OUT - stamped at *B's*
        #      start time, which is earlier than A's.
        #   3. Ordering by event_timestamp now reports CHECK_OUT before CHECK_IN,
        #      so the derived state is CHECKED_IN for a user who has checked out.
        #
        # The Phase 4 row lock serialises the *decision*; it cannot serialise a
        # timestamp that was fixed before the lock was taken. `clock_timestamp()`
        # reads the wall clock at insertion, so stored order always matches commit
        # order. It also makes the value distinct per statement, which `now()` is
        # not - two events written in one transaction shared a timestamp, leaving
        # the "latest event" query to break the tie arbitrarily.
        server_default=text("clock_timestamp()"),
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
