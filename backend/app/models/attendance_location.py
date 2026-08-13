"""AttendanceLocation model - the physical site where staff must be present."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Double,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.qr_challenge import QRChallenge
    from app.models.tenant import Tenant

#: Default geofence radius, in metres.
DEFAULT_GEOFENCE_RADIUS_METERS = 150

#: Default lifecycle status assigned to a newly created location.
LOCATION_STATUS_ACTIVE = "ACTIVE"


class AttendanceLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The single attendance site of a tenant.

    Karya V1 supports exactly **one** attendance location per tenant, enforced
    by a ``UNIQUE(tenant_id)`` constraint. Multiple locations are a later
    phase; relaxing that constraint is the only schema change required.

    No geofencing logic lives here - this model only records the geofence
    parameters.
    """

    __tablename__ = "attendance_locations"
    __table_args__ = (
        # One location per tenant (V1). Doubles as the tenant_id index.
        UniqueConstraint("tenant_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Double, nullable=False)
    longitude: Mapped[float] = mapped_column(Double, nullable=False)
    geofence_radius_meters: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_GEOFENCE_RADIUS_METERS,
        server_default=text(str(DEFAULT_GEOFENCE_RADIUS_METERS)),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LOCATION_STATUS_ACTIVE,
        server_default=text(f"'{LOCATION_STATUS_ACTIVE}'"),
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship(back_populates="attendance_locations")
    qr_challenges: Mapped[list[QRChallenge]] = relationship(
        back_populates="location",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AttendanceLocation id={self.id!s} tenant_id={self.tenant_id!s} name={self.name!r}>"
