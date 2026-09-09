"""A tenant's own attendance-location lifecycle: create once, update in place.

Split out of `app.api.v1.tenant` now that tenant management has grown past
"read/rename my own tenant" - business logic belongs here, not in the route
handler, matching every other domain in the codebase.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.attendance_location import AttendanceLocation


class AttendanceLocationExistsError(Exception):
    """The tenant already has an attendance location (V1 allows exactly one)."""


class NoAttendanceLocationError(Exception):
    """The tenant has no attendance location yet."""


def get_own_location(
    session: Session, *, tenant_id: uuid.UUID
) -> AttendanceLocation | None:
    """The tenant's attendance location, of any status, or ``None``.

    Unlike `app.services.presence.service.get_active_attendance_location`
    (which only ever wants an ACTIVE site to test a geofence against), an
    admin viewing their own settings should see it even if it were ever
    marked otherwise - there is no route that changes `status` today, but
    this reads the whole row rather than assuming ACTIVE.
    """
    return session.scalar(
        select(AttendanceLocation).where(AttendanceLocation.tenant_id == tenant_id)
    )


def create_own_location(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    name: str,
    latitude: float,
    longitude: float,
    geofence_radius_meters: int,
    description: str | None = None,
) -> AttendanceLocation:
    """Create the tenant's one attendance location.

    Raises:
        AttendanceLocationExistsError: one already exists.
    """
    if get_own_location(session, tenant_id=tenant_id) is not None:
        raise AttendanceLocationExistsError

    location = AttendanceLocation(
        tenant_id=tenant_id,
        name=name,
        description=description,
        latitude=latitude,
        longitude=longitude,
        geofence_radius_meters=geofence_radius_meters,
    )
    session.add(location)
    # The SELECT above is only a fast path for the common case - two
    # concurrent creates for a fresh tenant could both pass it. The
    # database's own UNIQUE(tenant_id) constraint is the real enforcement;
    # a nested transaction (SAVEPOINT) turns the loser's violation into a
    # clean domain error instead of an uncaught `IntegrityError` aborting
    # the whole request (see `app.services.users.service.create_user`).
    try:
        with session.begin_nested():
            session.flush()
    except IntegrityError as exc:
        raise AttendanceLocationExistsError from exc
    return location


def update_own_location(
    session: Session, *, tenant_id: uuid.UUID, changes: dict[str, Any]
) -> AttendanceLocation:
    """Update the tenant's existing attendance location.

    Raises:
        NoAttendanceLocationError: none exists yet - the caller should create
            one first.
    """
    location = get_own_location(session, tenant_id=tenant_id)
    if location is None:
        raise NoAttendanceLocationError

    for field, value in changes.items():
        setattr(location, field, value)
    return location
