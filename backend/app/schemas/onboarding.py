"""Request/response schemas for tenant self-service onboarding.

`extra="forbid"` everywhere, matching every other request model in this
codebase: a client trying to smuggle in `role` or `tenant_id` gets an
explicit 422 rather than having the field silently ignored.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.schemas.fields import (
    SLUG_MAX_LENGTH,
    TENANT_NAME_MAX_LENGTH,
    NormalizedEmail,
    PersonName,
    PlainPassword,
    trim,
)


def normalize_slug(value: object) -> object:
    """Trim and lower-case a tenant slug before validation.

    ``tenants.slug`` is globally unique and is what every employee types at
    login, so - like email - the casing someone happens to type must not
    decide whether ``Acme`` and ``acme`` are the same organization or two
    that collide unpredictably.
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


#: `^[a-z0-9]` then any run of lower-case letters/digits/hyphens, ending in
#: an alphanumeric - never a leading/trailing/doubled hyphen, since this
#: becomes part of the login form and a future URL.
_SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,%d}[a-z0-9])?$" % (SLUG_MAX_LENGTH - 2)

TenantSlug = Annotated[
    str,
    BeforeValidator(normalize_slug),
    Field(min_length=1, max_length=SLUG_MAX_LENGTH, pattern=_SLUG_PATTERN),
]

TenantName = Annotated[
    str, BeforeValidator(trim), Field(min_length=1, max_length=TENANT_NAME_MAX_LENGTH)
]


class TenantOnboardingRequest(BaseModel):
    """Body for ``POST /api/v1/onboarding/tenants``.

    Creates a new tenant and its first administrator in one transaction. The
    administrator is created ``INACTIVE`` and cannot sign in until the email
    address is verified - see
    :func:`app.services.onboarding.service.create_tenant_with_admin`.
    """

    model_config = ConfigDict(extra="forbid")

    organization_name: TenantName
    organization_slug: TenantSlug
    admin_name: PersonName
    admin_email: NormalizedEmail
    admin_password: PlainPassword


class TenantOnboardingResponse(BaseModel):
    """Deliberately carries no token: the account is not usable yet."""

    model_config = ConfigDict(extra="forbid")

    organization_slug: str
    message: str = "Check your email to verify your account before signing in."


class EmailVerificationRequest(BaseModel):
    """Body for ``POST /api/v1/onboarding/verify-email``."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


class ResendVerificationRequest(BaseModel):
    """Body for ``POST /api/v1/onboarding/resend-verification``.

    Identifies the account the same way login does - organization slug plus
    email - rather than a stale token, since the whole point is recovering
    from a link that's gone missing or expired.
    """

    model_config = ConfigDict(extra="forbid")

    organization_slug: TenantSlug
    admin_email: NormalizedEmail


class ResendVerificationResponse(BaseModel):
    """Always the same message, whether or not anything was actually sent -
    see :func:`app.services.onboarding.service.resend_verification_email`."""

    model_config = ConfigDict(extra="forbid")

    message: str = "If that account needs verifying, we've sent a new link."


__all__ = [
    "EmailVerificationRequest",
    "ResendVerificationRequest",
    "ResendVerificationResponse",
    "TenantName",
    "TenantOnboardingRequest",
    "TenantOnboardingResponse",
    "TenantSlug",
]
