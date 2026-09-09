"""Tenant self-service onboarding routes.

The two routes here are the only unauthenticated *write* endpoints in the
API. Both are thin - they validate the request, delegate to
:mod:`app.services.onboarding.service`, commit - matching every other route
module's division of labour.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.api.limits import EMAIL_VERIFICATION_RATE_LIMIT, ONBOARDING_RATE_LIMIT, RATE_LIMITED_RESPONSE
from app.schemas.auth import TokenResponse
from app.schemas.onboarding import (
    EmailVerificationRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    TenantOnboardingRequest,
    TenantOnboardingResponse,
)
from app.services.auth.service import issue_token_pair
from app.services.email.mailer import EmailDeliveryError
from app.services.onboarding import service as onboarding_service
from app.services.onboarding.service import SlugTakenError, VerificationError

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_SLUG_TAKEN_DETAIL = "That organization ID is already in use"
_VERIFICATION_FAILED_DETAIL = "This verification link is invalid or has expired"
_EMAIL_DELIVERY_FAILED_DETAIL = (
    "Could not send the verification email right now. Try again shortly."
)


@router.post(
    "/tenants",
    response_model=TenantOnboardingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization and its first administrator",
    dependencies=[ONBOARDING_RATE_LIMIT],
    responses={
        409: {"description": _SLUG_TAKEN_DETAIL},
        422: {"description": "Validation error"},
        503: {"description": _EMAIL_DELIVERY_FAILED_DETAIL},
        **RATE_LIMITED_RESPONSE,
    },
)
def create_tenant(
    payload: TenantOnboardingRequest, session: DbSession
) -> TenantOnboardingResponse:
    """Create a tenant and its first (unverified) TENANT_ADMIN.

    The new account cannot sign in until the emailed verification link is
    followed - see ``POST /onboarding/verify-email``. Nothing about the new
    account is returned here beyond the slug the admin will log in with;
    there is no token to hand back, since the account is not usable yet.
    """
    try:
        result = onboarding_service.create_tenant_with_admin(
            session,
            organization_name=payload.organization_name,
            organization_slug=payload.organization_slug,
            admin_name=payload.admin_name,
            admin_email=payload.admin_email,
            admin_password=payload.admin_password.get_secret_value(),
        )
    except SlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_SLUG_TAKEN_DETAIL
        ) from exc
    except EmailDeliveryError as exc:
        # The whole point of committing tenant+admin+token+email together is
        # that a failure here rolls all of it back - nobody ends up an
        # admin of a tenant they can never verify into. No explicit
        # `session.rollback()` needed: this exception propagates out of the
        # route, and `app.db.session.get_db` rolls back on any exception
        # that reaches it - `session.commit()` below is simply never
        # reached.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_EMAIL_DELIVERY_FAILED_DETAIL,
        ) from exc

    session.commit()
    return TenantOnboardingResponse(organization_slug=result.tenant.slug)


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    summary="Verify an onboarding email address and sign in",
    dependencies=[EMAIL_VERIFICATION_RATE_LIMIT],
    responses={
        401: {"description": _VERIFICATION_FAILED_DETAIL},
        **RATE_LIMITED_RESPONSE,
    },
)
def verify_email(
    payload: EmailVerificationRequest, session: DbSession
) -> TokenResponse:
    """Activate the account behind a verification token and sign it in.

    Returns the same token pair shape as ``POST /auth/login`` - the person
    who just proved they own this email address is, at this exact moment,
    as authenticated as anyone who just typed a correct password, so there
    is no reason to make them do that too.

    401, not 404 or 410: a token that never existed, one already consumed,
    and one that expired are all indistinguishable to the caller, the same
    anti-enumeration posture login itself uses for credentials.
    """
    try:
        user = onboarding_service.verify_email(session, raw_token=payload.token)
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_VERIFICATION_FAILED_DETAIL,
        ) from exc

    tokens = issue_token_pair(session, user=user)
    session.commit()
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    summary="Resend an onboarding verification email",
    dependencies=[EMAIL_VERIFICATION_RATE_LIMIT],
    responses={503: {"description": _EMAIL_DELIVERY_FAILED_DETAIL}, **RATE_LIMITED_RESPONSE},
)
def resend_verification(
    payload: ResendVerificationRequest, session: DbSession
) -> ResendVerificationResponse:
    """Issue a fresh verification link for a lost or expired one.

    Always returns the same message and 200, whether or not an email was
    actually sent - see
    :func:`app.services.onboarding.service.resend_verification_email` for
    why. Shares `verify-email`'s rate-limit budget: both are unauthenticated,
    per-IP, identity-guessing-shaped actions.

    The one exception to "always 200" is the mail server itself being
    unreachable (`EmailDeliveryError`) - that failure is identical no matter
    which organization/email was requested, so surfacing it as a 503 leaks
    nothing about whether the account exists.
    """
    try:
        onboarding_service.resend_verification_email(
            session,
            organization_slug=payload.organization_slug,
            admin_email=payload.admin_email,
        )
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_EMAIL_DELIVERY_FAILED_DETAIL,
        ) from exc

    session.commit()
    return ResendVerificationResponse()
