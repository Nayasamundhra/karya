"""Tenant model - one company/client using Karya."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendance_event import AttendanceEvent
    from app.models.attendance_location import AttendanceLocation
    from app.models.audit_log import AuditLog
    from app.models.qr_challenge import QRChallenge
    from app.models.refresh_token import RefreshToken
    from app.models.user import User

#: Default lifecycle status assigned to a newly created tenant.
TENANT_STATUS_ACTIVE = "ACTIVE"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single company/client. Root of every tenant-scoped record.

    Deletion policy: all business children (users, locations, attendance
    events, ...) use ``ON DELETE RESTRICT``, so a tenant with data cannot be
    deleted by accident. Audit logs use ``ON DELETE SET NULL`` so the audit
    trail outlives the tenant row.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TENANT_STATUS_ACTIVE,
        server_default=text(f"'{TENANT_STATUS_ACTIVE}'"),
    )

    # --- Relationships ------------------------------------------------------
    # `passive_deletes="all"` keeps SQLAlchemy from touching children on
    # delete, letting the RESTRICT foreign keys do their job.
    users: Mapped[list[User]] = relationship(
        back_populates="tenant",
        passive_deletes="all",
    )
    attendance_locations: Mapped[list[AttendanceLocation]] = relationship(
        back_populates="tenant",
        passive_deletes="all",
    )
    attendance_events: Mapped[list[AttendanceEvent]] = relationship(
        back_populates="tenant",
        passive_deletes="all",
    )
    # QR challenges are short-lived, disposable artefacts -> DB-level CASCADE.
    qr_challenges: Mapped[list[QRChallenge]] = relationship(
        back_populates="tenant",
        passive_deletes=True,
    )
    # Audit logs are retained; the FK is nulled rather than deleted.
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="tenant",
        passive_deletes=True,
    )
    # Authentication state -> DB-level CASCADE, like QR challenges.
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="tenant",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Tenant id={self.id!s} slug={self.slug!r}>"
