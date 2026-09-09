"""Tenant self-information routes.

Deliberately minimal. The tenant is always the caller's own - there is no
``tenant_id`` parameter anywhere - and only ``name`` is writable. Tenant creation,
suspension and deletion are operator actions, not something a tenant administrator
performs on themselves through the staff-management API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Annotated

from app.api.deps import CurrentUser, DbSession, require_roles
from app.api.limits import ADMIN_WRITE_RATE_LIMIT, RATE_LIMITED_RESPONSE
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.attendance_location import (
    AttendanceLocationCreateRequest,
    AttendanceLocationResponse,
    AttendanceLocationUpdateRequest,
)
from app.schemas.tenant import TenantResponse, TenantUpdateRequest
from app.services.tenant import service as tenant_service
from app.services.tenant.service import (
    AttendanceLocationExistsError,
    NoAttendanceLocationError,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])

TenantAdmin = Annotated[User, Depends(require_roles(UserRole.TENANT_ADMIN))]

_LOCATION_EXISTS_DETAIL = "An attendance location already exists for this tenant"
_NO_LOCATION_DETAIL = "No attendance location is configured yet"


def _load_own_tenant(session: DbSession, current_user: User) -> Tenant:
    """Fetch the caller's tenant by the id on their own user row."""
    tenant = session.get(Tenant, current_user.tenant_id)
    if tenant is None:  # pragma: no cover - implies a broken FK
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return tenant


@router.get(
    "/me",
    response_model=TenantResponse,
    summary="The caller's own tenant",
    responses={401: {"description": "Not authenticated"}},
)
def read_own_tenant(session: DbSession, current_user: CurrentUser) -> TenantResponse:
    """Return the tenant the authenticated user belongs to.

    Open to any active user: knowing which organisation you work for is not
    privileged. The response carries no user counts, credentials or configuration.
    """
    return TenantResponse.model_validate(_load_own_tenant(session, current_user))


@router.patch(
    "/me",
    response_model=TenantResponse,
    summary="Update the caller's own tenant",
    dependencies=[ADMIN_WRITE_RATE_LIMIT],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        **RATE_LIMITED_RESPONSE,
    },
)
def update_own_tenant(
    payload: TenantUpdateRequest, session: DbSession, current_user: TenantAdmin
) -> TenantResponse:
    """Update the tenant's display name.

    Only ``name``. ``slug`` is excluded despite looking like ordinary metadata: it
    is the identifier every employee types at login, so renaming it would lock out
    the whole company at once.
    """
    tenant = _load_own_tenant(session, current_user)
    for field, value in payload.changes().items():
        setattr(tenant, field, value)
    session.commit()
    return TenantResponse.model_validate(tenant)


@router.get(
    "/me/location",
    response_model=AttendanceLocationResponse,
    summary="The caller's own attendance location",
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": _NO_LOCATION_DETAIL},
    },
)
def read_own_location(
    session: DbSession, current_user: CurrentUser
) -> AttendanceLocationResponse:
    """Return the tenant's attendance location, if one has been set up.

    Open to any active user, like ``GET /tenant/me`` - the office address and
    geofence radius are operational context, not privileged configuration.
    """
    location = tenant_service.get_own_location(
        session, tenant_id=current_user.tenant_id
    )
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NO_LOCATION_DETAIL
        )
    return AttendanceLocationResponse.model_validate(location)


@router.post(
    "/me/location",
    response_model=AttendanceLocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Set up the caller's attendance location",
    dependencies=[ADMIN_WRITE_RATE_LIMIT],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        409: {"description": _LOCATION_EXISTS_DETAIL},
        **RATE_LIMITED_RESPONSE,
    },
)
def create_own_location(
    payload: AttendanceLocationCreateRequest,
    session: DbSession,
    current_user: TenantAdmin,
) -> AttendanceLocationResponse:
    """Create the tenant's one attendance location.

    Karya V1 supports exactly one per tenant (see
    `app.models.attendance_location`); call ``PATCH`` instead once one
    exists. Without this, check-in/out can never succeed for a fresh
    tenant - GPS verification has no geofence to test against.
    """
    try:
        location = tenant_service.create_own_location(
            session,
            tenant_id=current_user.tenant_id,
            name=payload.name,
            description=payload.description,
            latitude=payload.latitude,
            longitude=payload.longitude,
            geofence_radius_meters=payload.geofence_radius_meters,
        )
    except AttendanceLocationExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_LOCATION_EXISTS_DETAIL
        ) from exc

    session.commit()
    return AttendanceLocationResponse.model_validate(location)


@router.patch(
    "/me/location",
    response_model=AttendanceLocationResponse,
    summary="Update the caller's attendance location",
    dependencies=[ADMIN_WRITE_RATE_LIMIT],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _NO_LOCATION_DETAIL},
        **RATE_LIMITED_RESPONSE,
    },
)
def update_own_location(
    payload: AttendanceLocationUpdateRequest,
    session: DbSession,
    current_user: TenantAdmin,
) -> AttendanceLocationResponse:
    """Update the tenant's existing attendance location."""
    try:
        location = tenant_service.update_own_location(
            session, tenant_id=current_user.tenant_id, changes=payload.changes()
        )
    except NoAttendanceLocationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NO_LOCATION_DETAIL
        ) from exc

    session.commit()
    return AttendanceLocationResponse.model_validate(location)
