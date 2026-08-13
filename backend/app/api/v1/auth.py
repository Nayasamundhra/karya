"""Authentication routes.

These handlers are intentionally thin: validate the schema, delegate to
:mod:`app.services.auth.service`, translate the service's single
:class:`AuthenticationError` into a generic 401, commit. No credential logic
lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth import service as auth_service
from app.services.auth.service import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])

#: The one message returned for every credential failure. Saying no more than
#: this is what prevents tenant/user enumeration.
_INVALID_CREDENTIALS = "Invalid credentials"


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_INVALID_CREDENTIALS,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate within a tenant and obtain tokens",
    responses={401: {"description": _INVALID_CREDENTIALS}},
)
def login(payload: LoginRequest, session: DbSession) -> TokenResponse:
    """Exchange tenant slug + email + password for an access/refresh pair.

    Returns the same 401 whether the tenant is unknown, the user is unknown, the
    password is wrong, or the account is inactive.
    """
    try:
        tokens = auth_service.login(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
    except AuthenticationError as exc:
        raise _invalid_credentials() from exc

    session.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token for a new token pair",
    responses={401: {"description": _INVALID_CREDENTIALS}},
)
def refresh(payload: RefreshTokenRequest, session: DbSession) -> TokenResponse:
    """Rotate the supplied refresh token.

    The presented token is revoked as part of a successful rotation, so
    presenting it a second time fails. Rejection is never downgraded to
    "issue a new token anyway".
    """
    try:
        tokens = auth_service.refresh(
            session,
            raw_refresh_token=payload.refresh_token.get_secret_value(),
        )
    except AuthenticationError as exc:
        # Roll back the revocation attempt so a rejected rotation leaves no
        # partial state behind.
        session.rollback()
        raise _invalid_credentials() from exc

    session.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
def logout(payload: RefreshTokenRequest, session: DbSession) -> None:
    """Revoke the supplied refresh token.

    Idempotent, and returns 204 even for an unknown or already-revoked token so
    the endpoint cannot be used to probe which tokens exist. Access tokens are
    short-lived and are not blacklisted in this phase.
    """
    auth_service.logout(
        session, raw_refresh_token=payload.refresh_token.get_secret_value()
    )
    session.commit()


@router.get(
    "/me",
    response_model=UserResponse,
    summary="The authenticated user",
    responses={401: {"description": "Not authenticated"}},
)
def read_current_user(current_user: CurrentUser) -> UserResponse:
    """Return the caller's own profile.

    Identity comes exclusively from the validated bearer token; any ``user_id``,
    ``tenant_id`` or ``role`` supplied as a query parameter, header or body is
    ignored. The response never includes ``password_hash``.
    """
    return UserResponse.model_validate(current_user)
