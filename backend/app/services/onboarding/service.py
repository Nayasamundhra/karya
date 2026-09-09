"""Tenant self-service onboarding: create a tenant + its first administrator.

This is the one public, unauthenticated *write* endpoint anywhere in Karya,
so everything here is deliberately narrow:

* The created user's role is hardcoded to ``TENANT_ADMIN`` - never taken from
  the request. ``SUPER_ADMIN`` has no creation path anywhere in the system,
  onboarding included, matching the existing RBAC rule that a platform-level
  role is never implicitly granted.
* The account is created ``INACTIVE`` and stays that way until the email
  address is verified. This deliberately reuses existing machinery rather
  than inventing a new "unverified" state: `get_current_user` already
  refuses any non-ACTIVE user's token, and `authenticate_user` already
  returns the same generic failure for a wrong password, an unknown user, or
  a disabled account - an unverified admin is just one more member of that
  same indistinguishable set.
* Tenant, admin, and verification token are created in one transaction (the
  route commits), so a crash partway through can never leave an orphaned,
  loginless tenant sitting in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.tokens import generate_opaque_token, hash_opaque_token
from app.models.audit_log import AuditLog
from app.models.email_verification_token import EmailVerificationToken
from app.models.tenant import Tenant
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.email.mailer import send_email

ACTION_TENANT_ONBOARDED: Final[str] = "TENANT_ONBOARDED"
ACTION_EMAIL_VERIFIED: Final[str] = "EMAIL_VERIFIED"
ACTION_VERIFICATION_EMAIL_RESENT: Final[str] = "VERIFICATION_EMAIL_RESENT"

#: The onboarding admin's employee code. There is exactly one at creation
#: time and nothing else to disambiguate it by; a real employee-code scheme
#: is the tenant's own choice to make afterwards, through the ordinary
#: `POST /users` endpoint like every other hire.
_FIRST_ADMIN_EMPLOYEE_CODE: Final[str] = "ADMIN-1"


class SlugTakenError(Exception):
    """The requested organization slug is already in use."""


class VerificationError(Exception):
    """The verification token is missing, expired, or already used."""


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    tenant: Tenant
    admin: User


def _verification_url(config: Settings, raw_token: str) -> str:
    return f"{config.public_app_url}/onboarding/verify?token={raw_token}"


def create_tenant_with_admin(
    session: Session,
    *,
    organization_name: str,
    organization_slug: str,
    admin_name: str,
    admin_email: str,
    admin_password: str,
    config: Settings | None = None,
) -> OnboardingResult:
    """Create a tenant and its first, unverified TENANT_ADMIN.

    Raises:
        SlugTakenError: another tenant already uses this slug.
    """
    config = config or settings

    if session.scalar(select(Tenant).where(Tenant.slug == organization_slug)) is not None:
        raise SlugTakenError(organization_slug)

    tenant = Tenant(name=organization_name, slug=organization_slug)
    session.add(tenant)
    # The SELECT above is only a fast path for the common case - it cannot
    # stop two concurrent signups for the same slug from both passing it.
    # `tenants.slug` is the real enforcement (UNIQUE), and a nested
    # transaction (SAVEPOINT) here means a losing insert rolls back only
    # itself rather than aborting the whole request into an uncaught 500 -
    # the same pattern `app.services.users.service.create_user` uses for
    # duplicate email/employee_code.
    try:
        with session.begin_nested():
            session.flush()  # assigns tenant.id, needed by the rows below
    except IntegrityError as exc:
        raise SlugTakenError(organization_slug) from exc

    admin = User(
        tenant_id=tenant.id,
        employee_code=_FIRST_ADMIN_EMPLOYEE_CODE,
        name=admin_name,
        email=admin_email,
        password_hash=hash_password(admin_password),
        role=UserRole.TENANT_ADMIN,
        status=UserStatus.INACTIVE,
    )
    session.add(admin)
    session.flush()

    raw_token = generate_opaque_token()
    session.add(
        EmailVerificationToken(
            user_id=admin.id,
            tenant_id=tenant.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=config.email_verification_ttl_hours),
        )
    )

    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=admin.id,
            action=ACTION_TENANT_ONBOARDED,
            target_type=Tenant.__name__,
            target_id=tenant.id,
            log_metadata={"organization_slug": organization_slug},
        )
    )

    send_email(
        to=admin_email,
        subject="Verify your Karya account",
        body=(
            f"Welcome to Karya, {admin_name}.\n\n"
            f"Verify your account to finish setting up {organization_name}:\n"
            f"{_verification_url(config, raw_token)}\n\n"
            f"This link expires in {config.email_verification_ttl_hours} hours. "
            "If you didn't request this, you can ignore this email."
        ),
        config=config,
    )

    return OnboardingResult(tenant=tenant, admin=admin)


def verify_email(session: Session, *, raw_token: str) -> User:
    """Consume a verification token and activate its user.

    Single-use via the same atomic-``UPDATE`` pattern QR challenges use (see
    `app.services.presence.qr.consume_challenge`): the guard conditions and
    the write are one statement, so two concurrent redemptions of the same
    link can never both succeed.

    Raises:
        VerificationError: the token does not exist, is already consumed, or
            has expired.
    """
    claimed = session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.token_hash == hash_opaque_token(raw_token),
            EmailVerificationToken.consumed_at.is_(None),
            EmailVerificationToken.expires_at > datetime.now(UTC),
        )
        .values(consumed_at=datetime.now(UTC))
        .returning(EmailVerificationToken.id, EmailVerificationToken.user_id)
        .execution_options(synchronize_session=False)
    ).one_or_none()

    if claimed is None:
        raise VerificationError

    _, user_id = claimed
    user = session.get(User, user_id)
    if user is None:  # pragma: no cover - implies a broken FK
        raise VerificationError

    user.status = UserStatus.ACTIVE

    session.add(
        AuditLog(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action=ACTION_EMAIL_VERIFIED,
            target_type=User.__name__,
            target_id=user.id,
            log_metadata={},
        )
    )
    return user


def resend_verification_email(
    session: Session,
    *,
    organization_slug: str,
    admin_email: str,
    config: Settings | None = None,
) -> None:
    """Issue and send a fresh verification link, if doing so makes sense.

    Silently a no-op for an unknown organization, an unknown email, or an
    already-active account - the caller (see the route) returns the same
    generic response either way. Telling an anonymous, unauthenticated
    caller which of those is true would be an enumeration oracle over real
    organizations and email addresses, the same reason `verify_email` and
    login itself never distinguish "wrong" from "doesn't exist".

    Any previously issued, still-valid link for this account stops working
    the moment a fresh one is requested - so an old link that leaked (a
    forwarded email, a shared inbox) is superseded rather than left live
    alongside the new one.
    """
    config = config or settings

    tenant = session.scalar(select(Tenant).where(Tenant.slug == organization_slug))
    if tenant is None:
        return

    user = session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.email == admin_email)
    )
    if user is None or user.status != UserStatus.INACTIVE:
        return

    session.execute(
        update(EmailVerificationToken)
        .where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.consumed_at.is_(None),
        )
        .values(consumed_at=datetime.now(UTC))
    )

    raw_token = generate_opaque_token()
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=hash_opaque_token(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=config.email_verification_ttl_hours),
        )
    )

    session.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action=ACTION_VERIFICATION_EMAIL_RESENT,
            target_type=User.__name__,
            target_id=user.id,
            log_metadata={},
        )
    )

    send_email(
        to=admin_email,
        subject="Verify your Karya account",
        body=(
            f"Here is a new verification link for {tenant.name}:\n"
            f"{_verification_url(config, raw_token)}\n\n"
            f"This link expires in {config.email_verification_ttl_hours} hours, "
            "and any earlier link for this account no longer works. "
            "If you didn't request this, you can ignore this email."
        ),
        config=config,
    )
