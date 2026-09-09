"""Request/response schemas for a tenant's own attendance location.

Karya V1 supports exactly one attendance location per tenant (see
`app.models.attendance_location`), so this is a create-once,
update-in-place pair rather than a full collection API - there is
deliberately no list or delete endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.models.attendance_location import DEFAULT_GEOFENCE_RADIUS_METERS
from app.schemas.fields import LOCATION_DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH, trim, trim_or_none

LocationName = Annotated[
    str, BeforeValidator(trim), Field(min_length=1, max_length=NAME_MAX_LENGTH)
]

#: Optional free-text address/description (PRD §7). Never used by presence
#: verification - purely a human-facing label for the location, the same
#: way `AttendanceLocation.name` is.
#:
#: `max_length` is nested inside the `str` arm of the union (not applied to
#: `str | None` directly) - Pydantic v2 otherwise tries to run the length
#: check against `None` itself once `trim_or_none` maps an empty string to
#: it, and crashes with an unhandled `TypeError` instead of accepting the
#: value. Every submission that leaves this field blank hits exactly that
#: path, so this is not an edge case.
LocationDescription = Annotated[
    Annotated[str, Field(max_length=LOCATION_DESCRIPTION_MAX_LENGTH)] | None,
    BeforeValidator(trim_or_none),
]

#: Loose bounds, not a product opinion: 10m is smaller than most GPS error
#: budgets, 5000m is generous enough for a large campus while still catching
#: a fat-fingered "50000".
_MIN_RADIUS_METERS = 10
_MAX_RADIUS_METERS = 5_000


class AttendanceLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    description: str | None
    latitude: float
    longitude: float
    geofence_radius_meters: int
    status: str
    created_at: datetime
    updated_at: datetime


class AttendanceLocationCreateRequest(BaseModel):
    """Body for ``POST /api/v1/tenant/me/location``. Fails 409 if one exists."""

    model_config = ConfigDict(extra="forbid")

    name: LocationName
    description: LocationDescription = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    geofence_radius_meters: int = Field(
        default=DEFAULT_GEOFENCE_RADIUS_METERS,
        ge=_MIN_RADIUS_METERS,
        le=_MAX_RADIUS_METERS,
    )


class AttendanceLocationUpdateRequest(BaseModel):
    """Body for ``PATCH /api/v1/tenant/me/location``. Fails 404 if none exists."""

    model_config = ConfigDict(extra="forbid")

    name: LocationName | None = None
    description: LocationDescription = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    geofence_radius_meters: int | None = Field(
        default=None, ge=_MIN_RADIUS_METERS, le=_MAX_RADIUS_METERS
    )

    @model_validator(mode="after")
    def _require_a_change(self) -> AttendanceLocationUpdateRequest:
        if self.model_dump(exclude_unset=True, exclude_none=True) == {}:
            raise ValueError("no updatable field supplied")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)
