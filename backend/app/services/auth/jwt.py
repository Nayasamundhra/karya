"""JWT access-token minting and verification.

Access tokens are short-lived HS256 JWTs. They carry only what an authorisation
check needs (subject, tenant, role) plus standard registered claims - never an
email, password hash, secret or database detail.

The token *identifies* the caller; it is not treated as a source of truth for
their current role, status or tenant membership. Those come from the database in
:func:`app.api.deps.get_current_user`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt

from app.core.config import Settings, settings

#: Value of the custom ``type`` claim on an access token. Refresh tokens are
#: opaque random strings, never JWTs, so nothing else should ever appear here.
ACCESS_TOKEN_TYPE: Final[str] = "access"

#: Registered claims that must be present for a token to be considered valid.
_REQUIRED_CLAIMS: Final[list[str]] = ["sub", "exp", "iat", "jti"]


class InvalidTokenError(Exception):
    """A token was missing, malformed, expired, tampered with or of the wrong type.

    Intentionally carries no detail about *which* of those it was: the API layer
    turns any of them into the same generic 401 so a caller cannot probe the
    difference.
    """


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Validated claims of an access token."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
    jti: uuid.UUID
    issued_at: datetime
    expires_at: datetime


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    config: Settings | None = None,
) -> str:
    """Mint a signed access token for the given identity.

    Raises:
        RuntimeError: if no JWT secret is configured (see
            :attr:`app.core.config.Settings.jwt_secret`).
    """
    config = config or settings
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=config.access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "type": ACCESS_TOKEN_TYPE,
        "iat": issued_at,
        "exp": expires_at,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_access_token(
    token: str, *, config: Settings | None = None
) -> AccessTokenClaims:
    """Verify ``token`` and return its claims.

    Verifies the signature, the expiry, the presence of the required registered
    claims, and that ``type`` is exactly ``access``.

    Raises:
        InvalidTokenError: for any verification failure whatsoever.
    """
    config = config or settings
    if not config.is_auth_configured:
        # No secret => nothing can be trusted. Fail closed.
        raise InvalidTokenError("authentication is not configured")

    try:
        payload = jwt.decode(
            token,
            config.jwt_secret,
            algorithms=[config.jwt_algorithm],
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed, ...
        raise InvalidTokenError("could not validate token") from exc

    # A refresh token must never be usable as a bearer credential, and neither
    # must any future token type.
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("unexpected token type")

    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            tenant_id=uuid.UUID(payload["tenant_id"]),
            role=payload["role"],
            jti=uuid.UUID(payload["jti"]),
            issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidTokenError("malformed token claims") from exc
