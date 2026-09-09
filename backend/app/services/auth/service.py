"""Authentication business logic: login, token refresh, logout.

Route handlers stay thin - they validate the request schema, call one of these
functions, and translate :class:`AuthenticationError` into a generic 401.

Every failure mode raises the *same* exception type with no distinguishing
detail, which is what makes user enumeration impossible: a caller cannot tell
"no such tenant" from "no such user" from "wrong password" from "account
disabled".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
from app.services.auth import refresh_tokens as refresh_token_store
from app.services.auth.jwt import create_access_token
from app.services.auth.password import dummy_hash, verify_password


class AuthenticationError(Exception):
    """Authentication failed.

    Carries no reason by design; see the module docstring.
    """


@dataclass(frozen=True, slots=True)
class TokenPair:
    """The credentials returned by login and refresh."""

    access_token: str
    refresh_token: str
    expires_in: int


def _find_user_in_tenant(
    session: Session, *, tenant_slug: str, email: str
) -> User | None:
    """Find a user by email *within the tenant identified by slug*.

    The tenant is resolved first and its id constrains the user lookup, so a
    matching email in another tenant can never be returned. This is a single
    joined query rather than two round-trips, but the constraint is the same:
    ``users.tenant_id = tenants.id AND tenants.slug = :slug``.
    """
    return session.scalar(
        select(User)
        .join(Tenant, User.tenant_id == Tenant.id)
        .where(Tenant.slug == tenant_slug, User.email == email)
    )


def authenticate_user(
    session: Session, *, tenant_slug: str, email: str, password: str
) -> User:
    """Verify credentials and return the user.

    Raises:
        AuthenticationError: if the tenant or user does not exist, the password
            is wrong, or the account is not ACTIVE.
    """
    user = _find_user_in_tenant(session, tenant_slug=tenant_slug, email=email)

    if user is None:
        # Still perform one Argon2 verification so a missing tenant/user costs
        # the same wall-clock time as a wrong password. Without this, timing
        # alone reveals whether an account exists.
        verify_password(password, dummy_hash())
        raise AuthenticationError

    password_ok = verify_password(password, user.password_hash or "")

    # Check the password before the status check, and raise identically either
    # way, so response timing does not distinguish "disabled" from "wrong
    # password".
    if not password_ok or user.status != UserStatus.ACTIVE:
        raise AuthenticationError

    return user


def issue_token_pair(
    session: Session, *, user: User, config: Settings | None = None
) -> TokenPair:
    """Mint an access token plus a fresh refresh token for ``user``.

    Shared with `app.services.onboarding.service.verify_email`, which needs
    the exact same "just-authenticated, give them a session" step once a
    verification link is redeemed - not private to login/refresh anymore,
    but still owned by this module since it is the one place a token pair is
    minted.
    """
    config = config or settings
    issued = refresh_token_store.issue_refresh_token(
        session, user=user, config=config
    )
    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        config=config,
    )
    return TokenPair(
        access_token=access_token,
        refresh_token=issued.raw_token,
        expires_in=config.access_token_expire_seconds,
    )


def login(
    session: Session,
    *,
    tenant_slug: str,
    email: str,
    password: str,
    config: Settings | None = None,
) -> TokenPair:
    """Authenticate and issue a token pair.

    Raises:
        AuthenticationError: on any credential failure.
    """
    user = authenticate_user(
        session, tenant_slug=tenant_slug, email=email, password=password
    )
    return issue_token_pair(session, user=user, config=config)


def refresh(
    session: Session, *, raw_refresh_token: str, config: Settings | None = None
) -> TokenPair:
    """Rotate a refresh token, returning a brand-new pair.

    The presented token is revoked before the replacement is issued, so it can
    never be exchanged twice. A token that is unknown, already revoked, expired,
    or whose user has been removed or deactivated is rejected outright - it is
    never quietly exchanged for a new one.

    Raises:
        AuthenticationError: if the token or its user is not currently valid.
    """
    record = refresh_token_store.find_by_raw_token(session, raw_refresh_token)
    if record is None or not refresh_token_store.is_usable(record):
        # Covers replay of an already-rotated token: rotation revoked it, so
        # `is_usable` is False and this raises instead of issuing new tokens.
        raise AuthenticationError

    user = session.get(User, record.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError

    # Defence in depth: the stored tenant must still match the user's tenant.
    if record.tenant_id != user.tenant_id:
        raise AuthenticationError

    refresh_token_store.revoke(record)
    return issue_token_pair(session, user=user, config=config)


def logout(session: Session, *, raw_refresh_token: str) -> None:
    """Revoke the supplied refresh token.

    Idempotent and deliberately silent: an unknown or already-revoked token
    produces the same successful, empty outcome as a valid one, so the endpoint
    cannot be used to test whether a token exists. Access tokens are short-lived
    and are not blacklisted in this phase.
    """
    record = refresh_token_store.find_by_raw_token(session, raw_refresh_token)
    if record is not None:
        refresh_token_store.revoke(record)
