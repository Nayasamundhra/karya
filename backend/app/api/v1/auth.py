"""Authentication routes.

These handlers are intentionally thin: validate the schema, delegate to
:mod:`app.services.auth.service`, translate the service's single
:class:`AuthenticationError` into a generic 401, commit. No credential logic
lives here.

Phase 7 adds two things and changes no behaviour:

* **Rate limiting** - a per-address ceiling on request volume, plus a per-identity
  ceiling on *failed* logins. See :mod:`app.api.limits` for why both, and for the
  trade-off the second one carries.
* **Structured logging** - one event per outcome, carrying the tenant slug and
  never the email, the password or either token. Authentication is the one place
  where logging too much is worse than logging too little, so the fields are
  chosen explicitly rather than by dumping the request.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import CurrentUser, DbSession
from app.api.limits import (
    LOGIN_RATE_LIMIT,
    RATE_LIMITED_RESPONSE,
    REFRESH_RATE_LIMIT,
    clear_login_failures,
    client_identity,
    guard_login_failures,
    record_login_failure,
)
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.auth import service as auth_service
from app.services.auth.service import AuthenticationError

logger = logging.getLogger(__name__)

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
    dependencies=[LOGIN_RATE_LIMIT],
    responses={401: {"description": _INVALID_CREDENTIALS}, **RATE_LIMITED_RESPONSE},
)
def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    """Exchange tenant slug + email + password for an access/refresh pair.

    Returns the same 401 whether the tenant is unknown, the user is unknown, the
    password is wrong, or the account is inactive.

    Failed attempts are counted per (tenant, email) and the counter is cleared on
    success, so repeated guessing against one account is throttled while a person
    who mistypes once and then succeeds is not. The 429 that throttling produces is
    identical for an account that exists and one that does not - the
    anti-enumeration property has to hold for every status code, not only 401.
    """
    guard_login_failures(payload.tenant_slug, payload.email)
    try:
        tokens = auth_service.login(
            session,
            tenant_slug=payload.tenant_slug,
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
    except AuthenticationError as exc:
        record_login_failure(payload.tenant_slug, payload.email)
        # The tenant slug is a public identifier (staff type it at login) and is
        # what an operator correlates an attack by. The email is deliberately
        # absent: it identifies a person, and a log of attempted addresses is a
        # list of accounts worth attacking.
        logger.warning(
            "login_failed",
            extra={
                "event": "login_failed",
                "tenant_slug": payload.tenant_slug,
                "client_ip": client_identity(request),
            },
        )
        raise _invalid_credentials() from exc

    clear_login_failures(payload.tenant_slug, payload.email)
    session.commit()
    logger.info(
        "login_succeeded",
        extra={"event": "login_succeeded", "tenant_slug": payload.tenant_slug},
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate a refresh token for a new token pair",
    dependencies=[REFRESH_RATE_LIMIT],
    responses={401: {"description": _INVALID_CREDENTIALS}, **RATE_LIMITED_RESPONSE},
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
        # No token, hash or prefix is logged. A rejected rotation is interesting in
        # aggregate (it can mean a stolen token is being replayed); the value that
        # was presented adds nothing an operator can act on and everything an
        # attacker could reuse if the log leaked.
        logger.warning("refresh_rejected", extra={"event": "refresh_rejected"})
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
    # Shares the refresh bucket: both are unauthenticated endpoints that turn an
    # opaque token into a database lookup, so they are the same abuse surface and
    # one budget for the pair is easier to reason about than two.
    dependencies=[REFRESH_RATE_LIMIT],
    responses={**RATE_LIMITED_RESPONSE},
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
