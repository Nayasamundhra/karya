"""User model - a staff member, manager or administrator within a tenant."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.attendance_event import AttendanceEvent
    from app.models.audit_log import AuditLog
    from app.models.refresh_token import RefreshToken
    from app.models.tenant import Tenant


class UserRole(enum.StrEnum):
    """Roles a user may hold. Enforcement (RBAC) is a later phase."""

    SUPER_ADMIN = "SUPER_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    MANAGER = "MANAGER"
    STAFF = "STAFF"


class UserStatus(enum.StrEnum):
    """Lifecycle status of a user account."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person belonging to exactly one tenant.

    ``employee_code`` and ``email`` are unique *per tenant*, not globally: the
    same person may exist in two tenants with the same email address.

    Only ``password_hash`` is ever stored - there is deliberately no
    plain-text password column. It is nullable in this phase because
    authentication has not been implemented yet.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "employee_code"),
        UniqueConstraint("tenant_id", "email"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=UserRole.STAFF,
        server_default=text(f"'{UserRole.STAFF.value}'"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=text(f"'{UserStatus.ACTIVE.value}'"),
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship(back_populates="users")
    attendance_events: Mapped[list[AttendanceEvent]] = relationship(
        back_populates="user",
        passive_deletes="all",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="actor",
        foreign_keys="AuditLog.actor_user_id",
        passive_deletes=True,
    )
    # Authentication state, not history: the DB-level CASCADE removes sessions
    # with the user.
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id!s} tenant_id={self.tenant_id!s} email={self.email!r}>"
