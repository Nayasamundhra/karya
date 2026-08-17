"""Request/response schemas for the authentication endpoints.

Every request model sets ``extra="forbid"``. That is a security decision, not
tidiness: a client that tries to smuggle in ``tenant_id``, ``role`` or
``user_id`` gets an explicit 422 rather than having the field silently ignored,
so an attempted privilege or tenant escalation fails loudly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.fields import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    SLUG_MAX_LENGTH,
    NormalizedEmail,
)

# Kept as module-level aliases so existing imports and tests continue to work;
# the values themselves now live in `app.schemas.fields` so login and user
# management cannot drift apart.
_SLUG_MAX_LENGTH = SLUG_MAX_LENGTH
_PASSWORD_MIN_LENGTH = PASSWORD_MIN_LENGTH
_PASSWORD_MAX_LENGTH = PASSWORD_MAX_LENGTH


class LoginRequest(BaseModel):
    """Credentials for ``POST /api/v1/auth/login``.

    The tenant is identified by slug: login is tenant-scoped, and the user
    lookup is constrained to the resolved tenant.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_slug: str = Field(min_length=1, max_length=_SLUG_MAX_LENGTH)
    #: Normalised to lower-case, so the casing someone types cannot decide
    #: whether they can log in. See `app.schemas.fields.normalize_email`.
    email: NormalizedEmail
    #: SecretStr so the value cannot surface in a validation error or log line.
    password: SecretStr = Field(
        min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH
    )


class RefreshTokenRequest(BaseModel):
    """Body for ``POST /api/v1/auth/refresh`` and ``.../logout``."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: SecretStr = Field(min_length=1)


class TokenResponse(BaseModel):
    """Credentials returned by login and refresh.

    ``refresh_token`` is the only time the raw value is ever exposed; the server
    keeps just its hash.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    #: Access-token lifetime in seconds (e.g. 900 for the 15-minute default).
    expires_in: int
