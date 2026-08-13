"""AuditLog model - append-only trail of privileged actions.

Audit-logging business logic (who writes what, and when) is a later phase.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One recorded action, e.g. ``USER_CREATED`` or ``ATTENDANCE_CORRECTED``.

    ``tenant_id`` and ``actor_user_id`` are nullable so platform-level actions
    (no tenant) and system-initiated actions (no human actor) can be recorded.
    Both use ``ON DELETE SET NULL``: the trail must survive the deletion of the
    tenant or actor it refers to.

    ``target_id`` is an untyped UUID paired with ``target_type`` rather than a
    foreign key, because the target may be any entity - including one that has
    since been deleted.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_id", "tenant_id"),
        Index("ix_audit_logs_actor_user_id", "actor_user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # The attribute is `log_metadata` because `metadata` is reserved by
    # SQLAlchemy's declarative API; the database column is still `metadata`.
    log_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant | None] = relationship(back_populates="audit_logs")
    actor: Mapped[User | None] = relationship(
        back_populates="audit_logs",
        foreign_keys=[actor_user_id],
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog id={self.id!s} action={self.action!r} target={self.target_type!r}>"
