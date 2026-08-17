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
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.schemas.tenant import TenantResponse, TenantUpdateRequest

router = APIRouter(prefix="/tenant", tags=["tenant"])

TenantAdmin = Annotated[User, Depends(require_roles(UserRole.TENANT_ADMIN))]


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
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
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
