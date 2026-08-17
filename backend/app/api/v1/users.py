"""User management and self-service account routes.

Two audiences, two authorization levels:

* **Self-service** (`/users/me...`) - any authenticated active user, acting only
  on themselves. There is no user id in these paths, so nothing to redirect.
* **Administration** (`/users`, `/users/{user_id}...`) - `TENANT_ADMIN` only,
  acting only within their own tenant.

`MANAGER` deliberately gets **no** user-management powers. Managers see attendance;
tenant admins own identity and lifecycle. Keeping that separation means a manager
account, which is handed out far more freely, cannot create logins or change
roles.

Route order matters here: `/users/me` is declared before `/users/{user_id}` so
that "me" is matched as a literal rather than being parsed as a UUID.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, require_roles
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import (
    PasswordChangeRequest,
    PasswordChangeResponse,
    RoleUpdateRequest,
    SelfUpdateRequest,
    UserAuditEntryResponse,
    UserAuditResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserListPagination,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.users import errors, service as users_service

router = APIRouter(prefix="/users", tags=["users"])

#: Identity and lifecycle are the tenant administrator's job alone.
TenantAdmin = Annotated[User, Depends(require_roles(UserRole.TENANT_ADMIN))]

_USER_NOT_FOUND = "User not found"

PageParam = Annotated[int, Query(ge=1, description="1-based page number")]
PageSizeParam = Annotated[
    int,
    Query(ge=1, le=users_service.MAX_PAGE_SIZE, description="Items per page"),
]


def _not_found() -> HTTPException:
    """The single 404 used for absent and cross-tenant users alike."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail=_USER_NOT_FOUND
    )


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _pagination(page: int, page_size: int, total: int) -> UserListPagination:
    return UserListPagination(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=-(-total // page_size) if page_size else 0,
    )


# ---------------------------------------------------------------------------
# Self-service - declared first so "me" is not read as a user id
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The caller's own profile",
    responses={401: {"description": "Not authenticated"}},
)
def read_own_profile(current_user: CurrentUser) -> UserResponse:
    """Return the authenticated user's profile.

    Identity comes from the bearer token; no id is accepted. Never includes
    ``password_hash`` or any token.
    """
    return UserResponse.model_validate(current_user)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update the caller's own profile",
    responses={401: {"description": "Not authenticated"}},
)
def update_own_profile(
    payload: SelfUpdateRequest, session: DbSession, current_user: CurrentUser
) -> UserResponse:
    """Update the caller's own safe profile fields.

    Only ``name`` is writable here. Role, status, tenant and email are not - they
    are administrative or identity concerns, and a schema that never declares them
    rejects an attempt to send one with a 422.
    """
    user = users_service.update_user_profile(
        session,
        tenant_id=current_user.tenant_id,
        actor=current_user,
        user_id=current_user.id,
        changes=payload.changes(),
    )
    session.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/me/password",
    response_model=PasswordChangeResponse,
    summary="Change the caller's own password",
    responses={
        400: {"description": "New password rejected"},
        401: {"description": "Not authenticated, or current password incorrect"},
    },
)
def change_own_password(
    payload: PasswordChangeRequest, session: DbSession, current_user: CurrentUser
) -> PasswordChangeResponse:
    """Change the authenticated user's password.

    The current password is verified before anything about the new one is
    considered, so the endpoint answers no questions for a caller who has not
    proven they own the account. A wrong current password returns 401 with a
    generic message - never a hint about the new password's acceptability.

    Every refresh session is revoked on success: a password change usually means
    the old one is suspect, and a 30-day refresh token would otherwise keep
    whoever knew it signed in.
    """
    try:
        revoked = users_service.change_own_password(
            session,
            user=current_user,
            current_password=payload.current_password.get_secret_value(),
            new_password=payload.new_password.get_secret_value(),
        )
    except errors.InvalidCurrentPasswordError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc
    except errors.PasswordUnchangedError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        ) from exc
    except errors.PasswordTooSimilarError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must not match your email or employee code",
        ) from exc

    session.commit()
    return PasswordChangeResponse(sessions_revoked=revoked)


# ---------------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=UserDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user in the caller's tenant",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        409: {"description": "Email or employee code already in use"},
    },
)
def create_user(
    payload: UserCreateRequest, session: DbSession, current_user: TenantAdmin
) -> UserDetailResponse:
    """Create a user inside the administrator's own tenant.

    The tenant is taken from the authenticated administrator - there is no
    ``tenant_id`` field, so a user cannot be created anywhere else. The password is
    hashed with Argon2id and never echoed back.

    A duplicate email or employee code surfaces as a clean 409; the underlying
    constraint violation never reaches the client.
    """
    try:
        user = users_service.create_user(
            session,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            email=payload.email,
            password=payload.password.get_secret_value(),
            name=payload.name,
            employee_code=payload.employee_code,
            role=payload.role,
        )
    except errors.EmailAlreadyExistsError as exc:
        session.rollback()
        raise _conflict("A user with that email already exists") from exc
    except errors.EmployeeCodeAlreadyExistsError as exc:
        session.rollback()
        raise _conflict("A user with that employee code already exists") from exc

    session.commit()
    return UserDetailResponse.model_validate(user)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users in the caller's tenant",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
    },
)
def list_users(
    session: DbSession,
    current_user: TenantAdmin,
    search: Annotated[
        str | None, Query(max_length=255, description="Match name, email or code")
    ] = None,
    role: Annotated[UserRole | None, Query(description="Filter by role")] = None,
    user_status: Annotated[
        UserStatus | None, Query(alias="status", description="Filter by status")
    ] = None,
    page: PageParam = 1,
    page_size: PageSizeParam = users_service.DEFAULT_PAGE_SIZE,
) -> UserListResponse:
    """One page of the caller's own tenant's users.

    Filtering and search happen in SQL - the tenant is never loaded into memory to
    be sifted - and the search term is a bound parameter, so wildcards and quotes
    are matched literally rather than altering the query. Page size is capped.
    """
    users, total = users_service.list_users(
        session,
        tenant_id=current_user.tenant_id,
        search=search,
        role=role,
        status=user_status,
        page=page,
        page_size=page_size,
    )
    return UserListResponse(
        items=[UserDetailResponse.model_validate(u) for u in users],
        pagination=_pagination(page, page_size, total),
    )


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="Read one user in the caller's tenant",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
    },
)
def read_user(
    user_id: uuid.UUID, session: DbSession, current_user: TenantAdmin
) -> UserDetailResponse:
    """Read one user from the caller's own tenant.

    An id belonging to another tenant returns 404, identical to an id that exists
    nowhere - distinguishing them would confirm the id is real and allow
    cross-tenant enumeration.
    """
    try:
        user = users_service.get_user(
            session, tenant_id=current_user.tenant_id, user_id=user_id
        )
    except errors.UserNotFoundError as exc:
        raise _not_found() from exc
    return UserDetailResponse.model_validate(user)


@router.patch(
    "/{user_id}",
    response_model=UserDetailResponse,
    summary="Update one user's profile",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
        409: {"description": "Email or employee code already in use"},
    },
)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    session: DbSession,
    current_user: TenantAdmin,
) -> UserDetailResponse:
    """Update a user's profile fields.

    Writable: ``email``, ``name``, ``employee_code``. Not writable here: ``role``
    and ``status``, which have dedicated endpoints so a privilege change is never
    indistinguishable from a typo correction in the audit trail.
    """
    try:
        user = users_service.update_user_profile(
            session,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            user_id=user_id,
            changes=payload.changes(),
        )
    except errors.UserNotFoundError as exc:
        raise _not_found() from exc
    except errors.EmailAlreadyExistsError as exc:
        session.rollback()
        raise _conflict("A user with that email already exists") from exc
    except errors.EmployeeCodeAlreadyExistsError as exc:
        session.rollback()
        raise _conflict("A user with that employee code already exists") from exc

    session.commit()
    return UserDetailResponse.model_validate(user)


@router.patch(
    "/{user_id}/role",
    response_model=UserDetailResponse,
    summary="Change one user's role",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions, or changing your own role"},
        404: {"description": _USER_NOT_FOUND},
        409: {"description": "Would leave the tenant without an administrator"},
    },
)
def change_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    session: DbSession,
    current_user: TenantAdmin,
) -> UserDetailResponse:
    """Change a user's role within the caller's tenant.

    Refused if the target is the caller: nobody edits their own role, which closes
    the most direct escalation path. Also refused if it would demote the tenant's
    last active administrator. ``SUPER_ADMIN`` is not an assignable role.
    """
    try:
        user = users_service.change_user_role(
            session,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            user_id=user_id,
            new_role=payload.role,
        )
    except errors.UserNotFoundError as exc:
        raise _not_found() from exc
    except errors.SelfRoleChangeError as exc:
        raise _forbidden("You cannot change your own role") from exc
    except errors.LastAdminError as exc:
        session.rollback()
        raise _conflict(
            "The tenant must retain at least one active administrator"
        ) from exc

    session.commit()
    return UserDetailResponse.model_validate(user)


def _set_status(
    session: DbSession,
    current_user: User,
    user_id: uuid.UUID,
    new_status: UserStatus,
) -> UserDetailResponse:
    """Shared body for activate and deactivate."""
    try:
        user = users_service.set_user_status(
            session,
            tenant_id=current_user.tenant_id,
            actor=current_user,
            user_id=user_id,
            status=new_status,
        )
    except errors.UserNotFoundError as exc:
        raise _not_found() from exc
    except errors.SelfDeactivationError as exc:
        raise _forbidden("You cannot deactivate your own account") from exc
    except errors.LastAdminError as exc:
        session.rollback()
        raise _conflict(
            "The tenant must retain at least one active administrator"
        ) from exc

    session.commit()
    return UserDetailResponse.model_validate(user)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserDetailResponse,
    summary="Deactivate a user",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions, or deactivating yourself"},
        404: {"description": _USER_NOT_FOUND},
        409: {"description": "Would leave the tenant without an administrator"},
    },
)
def deactivate_user(
    user_id: uuid.UUID, session: DbSession, current_user: TenantAdmin
) -> UserDetailResponse:
    """Deactivate a user - a lifecycle change, never a delete.

    The account can no longer log in, refresh, check in or check out, and its
    refresh sessions are revoked immediately. Attendance events and audit rows are
    untouched, so history stays complete and still resolves to a real identity.
    """
    return _set_status(session, current_user, user_id, UserStatus.INACTIVE)


@router.post(
    "/{user_id}/activate",
    response_model=UserDetailResponse,
    summary="Reactivate a user",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
    },
)
def activate_user(
    user_id: uuid.UUID, session: DbSession, current_user: TenantAdmin
) -> UserDetailResponse:
    """Reactivate a user, restoring their ability to authenticate.

    Their password is left alone - reactivation is not a credential reset, and
    silently clearing one would lock the person out instead.
    """
    return _set_status(session, current_user, user_id, UserStatus.ACTIVE)


@router.get(
    "/{user_id}/audit",
    response_model=UserAuditResponse,
    summary="One user's lifecycle audit history",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": _USER_NOT_FOUND},
    },
)
def read_user_audit(
    user_id: uuid.UUID,
    session: DbSession,
    current_user: TenantAdmin,
    page: PageParam = 1,
    page_size: PageSizeParam = users_service.DEFAULT_PAGE_SIZE,
) -> UserAuditResponse:
    """Lifecycle audit rows for one user, newest first.

    Scoped to the tenant, to ``target_type='User'`` and to this user, so it is not
    a window onto the tenant's whole audit log - attendance and QR rows are not
    reachable here. The metadata contains only identifiers and before/after values.
    """
    try:
        user = users_service.get_user(
            session, tenant_id=current_user.tenant_id, user_id=user_id
        )
    except errors.UserNotFoundError as exc:
        raise _not_found() from exc

    entries, total = users_service.list_user_audit(
        session,
        tenant_id=current_user.tenant_id,
        user_id=user.id,
        page=page,
        page_size=page_size,
    )
    return UserAuditResponse(
        user_id=user.id,
        items=[
            UserAuditEntryResponse(
                id=entry.id,
                action=entry.action,
                actor_user_id=entry.actor_user_id,
                created_at=entry.created_at,
                metadata=entry.log_metadata,
            )
            for entry in entries
        ],
        pagination=_pagination(page, page_size, total),
    )
