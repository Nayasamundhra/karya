"""Shared FastAPI dependencies: database session, current user, RBAC.

This is the single place authentication is enforced. Route handlers never decode
a token themselves, so there is exactly one implementation to audit.

Two rules are load-bearing here:

1. **The token identifies; the database decides.** A JWT proves *who* is
   calling. Their status, role and tenant membership are re-read from PostgreSQL
   on every request, so deactivating a user or changing their role takes effect
   immediately rather than when their token happens to expire.
2. **Tenant context is never accepted from the client.** It is derived from the
   authenticated user's row. No path, query, header or body value can influence
   it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User, UserRole, UserStatus
from app.services.auth.jwt import InvalidTokenError, decode_access_token

#: `auto_error=False` so a missing/!bearer header reaches our own handler and
#: gets the same generic 401 (with WWW-Authenticate) as an invalid token.
_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

DbSession = Annotated[Session, Depends(get_db)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
]


def _unauthorized() -> HTTPException:
    """The one 401 used for every authentication failure.

    Identical for missing, malformed, expired, wrong-type and tampered tokens,
    and for users who have since been deleted or deactivated - so a caller
    cannot distinguish them.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    session: DbSession, credentials: BearerCredentials = None
) -> User:
    """Resolve and validate the caller, returning their database row.

    Verifies the bearer token's signature, expiry and ``type``, then loads the
    user and re-checks the authoritative state:

    * the user still exists,
    * the user is ``ACTIVE``, and
    * the token's ``tenant_id`` still matches the user's tenant.

    That last check is a consistency guard, not the source of tenant context:
    the returned ``user.tenant_id`` is what callers must scope queries by. It
    catches a token whose tenant claim has gone stale (or been forged against a
    leaked secret) and refuses it rather than trusting either side blindly.

    Raises:
        HTTPException: 401 for any failure.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized() from exc

    user = session.get(User, claims.user_id)
    if user is None:
        raise _unauthorized()

    # The database is authoritative for status. A token issued while the account
    # was active stops working the moment it is deactivated.
    if user.status != UserStatus.ACTIVE:
        raise _unauthorized()

    if claims.tenant_id != user.tenant_id:
        raise _unauthorized()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_tenant_id(current_user: CurrentUser) -> uuid.UUID:
    """The authenticated tenant context, derived solely from the database user.

    Depend on this (or on ``current_user.tenant_id``) whenever a query touches
    a tenant-owned table. See :mod:`app.db.tenant_scope`.
    """
    return current_user.tenant_id


CurrentTenantId = Annotated[uuid.UUID, Depends(get_current_tenant_id)]


def require_roles(*allowed_roles: UserRole) -> Callable[[User], User]:
    """Build a dependency that admits only the listed roles.

        @router.get("/staff", dependencies=[Depends(require_roles(UserRole.MANAGER))])

    or, to also use the user:

        user: Annotated[User, Depends(require_roles(UserRole.TENANT_ADMIN))]

    Membership is an **exact set match, with no hierarchy**: MANAGER does not
    satisfy a TENANT_ADMIN requirement, and ``SUPER_ADMIN`` is not implicitly
    granted either - a platform-level role must be listed explicitly to be
    accepted. Silent inheritance is how over-broad access creeps in, so each
    route states exactly who may call it.

    The role is read from the database row, never from the token claim, so a
    role change applies to the very next request.
    """
    if not allowed_roles:
        raise ValueError("require_roles() needs at least one role")
    permitted = frozenset(role.value for role in allowed_roles)

    def dependency(current_user: CurrentUser) -> User:
        if current_user.role not in permitted:
            # 403, not 401: the caller is authenticated, just not permitted.
            # The message names no role, so probing reveals no policy detail.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return dependency
