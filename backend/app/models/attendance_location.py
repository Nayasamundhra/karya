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
    from app.models.tenant import Tenant

#: Default geofence radius, in metres.
DEFAULT_GEOFENCE_RADIUS_METERS = 150

#: Default cutoff for the forgotten-checkout safety net, in hours. A tenant's
#: own value (below) is what actually governs their staff; this is only the
#: value a freshly created location gets and the fallback for the
#: practically-unreachable case of a stale session outliving its location -
#: not an industry figure, just a starting point a tenant admin can change.
DEFAULT_MAX_SHIFT_HOURS = 16

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
        UniqueConstraint("qr_token"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Optional free-text address/description (PRD §7) - purely a
    #: human-facing label, never read by presence verification.
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
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
    #: Static, never-expiring token printed/displayed as this location's QR
    #: code. It identifies *which* location a scan is against - it proves
    #: nothing about proximity to a screen the way the old rotating challenge
    #: did, so it is not a secret in that sense. `UNIQUE` (see
    #: `__table_args__`) is what lets a scan resolve straight to one location
    #: without also being told a tenant. Regenerating it (see
    #: `app.services.tenant.service.regenerate_location_qr_token`) is the
    #: only lever against a leaked/misused code, since there is no rotation
    #: left to age it out on its own.
    qr_token: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    #: A CHECK_IN still open after this many hours is auto-closed - see
    #: `app.services.attendance.service.close_stale_session_if_needed`. Lives
    #: here, not in global settings, for the same reason
    #: `geofence_radius_meters` does: what counts as "forgotten" is a
    #: site-specific call, not a platform-wide one - 24h on-call staff and a
    #: 9-to-5 office need genuinely different numbers.
    max_shift_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MAX_SHIFT_HOURS,
        server_default=text(str(DEFAULT_MAX_SHIFT_HOURS)),
    )

    # --- Relationships ------------------------------------------------------
    tenant: Mapped[Tenant] = relationship(back_populates="attendance_locations")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AttendanceLocation id={self.id!s} tenant_id={self.tenant_id!s} name={self.name!r}>"
