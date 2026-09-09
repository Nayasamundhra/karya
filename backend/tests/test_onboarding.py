"""Tenant self-service onboarding: the one public, unauthenticated write
surface in the API.

Covers: a fresh signup creates an INACTIVE admin nobody can log in as yet,
verification activates exactly that admin and signs them in, and every
failure mode (duplicate slug, bad/expired/replayed token, smuggled fields,
rate limiting) behaves the way the rest of the API already does for the
equivalent situation - generic anti-enumeration failures, 422 on smuggling,
429 with `Retry-After` when hammered.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Tenant, User, UserRole, UserStatus
from app.models.email_verification_token import EmailVerificationToken

ONBOARD_PATH = "/api/v1/onboarding/tenants"
VERIFY_PATH = "/api/v1/onboarding/verify-email"
RESEND_PATH = "/api/v1/onboarding/resend-verification"


def _payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "organization_name": "Acme Technologies",
        "organization_slug": "acme-onboard",
        "admin_name": "Ada Lovelace",
        "admin_email": "ada@acme-onboard.com",
        "admin_password": "correct-horse-battery-staple",
    }
    body.update(overrides)
    return body


def _extract_verification_link(caplog: pytest.LogCaptureFixture) -> str:
    """Pull the emailed link out of the dev-mode mailer fallback log line.

    `send_email` logs the full body only when SMTP is unconfigured (the
    default in this test environment) - see `app.services.email.mailer`.
    """
    for record in caplog.records:
        if getattr(record, "event", None) == "email_not_sent_no_smtp_configured":
            body = record.body
            for line in body.splitlines():
                if "token=" in line:
                    return line.strip()
    raise AssertionError("no verification email was logged")


def _token_from_link(link: str) -> str:
    return link.rsplit("token=", 1)[1]


def test_onboarding_creates_inactive_admin_and_emails_a_verification_link(
    client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        response = client.post(ONBOARD_PATH, json=_payload())

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "organization_slug": "acme-onboard",
        "message": "Check your email to verify your account before signing in.",
    }

    tenant = db_session.scalar(select(Tenant).where(Tenant.slug == "acme-onboard"))
    assert tenant is not None
    assert tenant.name == "Acme Technologies"

    admin = db_session.scalar(select(User).where(User.tenant_id == tenant.id))
    assert admin is not None
    assert admin.role == UserRole.TENANT_ADMIN.value
    # Not usable yet - the whole point of email verification.
    assert admin.status == UserStatus.INACTIVE.value
    assert admin.email == "ada@acme-onboard.com"

    verification = db_session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == admin.id)
    )
    assert verification is not None
    assert verification.consumed_at is None

    # The link was genuinely emailed (logged, in this unconfigured-SMTP test
    # environment) rather than merely persisted server-side.
    link = _extract_verification_link(caplog)
    assert "/onboarding/verify?token=" in link


def test_onboarding_rejects_a_slug_already_in_use(client: TestClient) -> None:
    first = client.post(ONBOARD_PATH, json=_payload())
    assert first.status_code == 201

    second = client.post(
        ONBOARD_PATH, json=_payload(admin_email="someone-else@acme-onboard.com")
    )
    assert second.status_code == 409


def test_onboarding_normalizes_slug_casing(
    client: TestClient, db_session: Session
) -> None:
    response = client.post(ONBOARD_PATH, json=_payload(organization_slug="ACME-Onboard"))
    assert response.status_code == 201
    assert response.json()["organization_slug"] == "acme-onboard"

    # A second signup with different casing of the same slug collides, the
    # same way `normalize_email` makes login case-insensitive on stored data.
    conflict = client.post(
        ONBOARD_PATH,
        json=_payload(
            organization_slug="acme-onboard", admin_email="second@acme-onboard.com"
        ),
    )
    assert conflict.status_code == 409


@pytest.mark.parametrize(
    "bad_slug", ["-leading-hyphen", "trailing-hyphen-", "has a space", "UP PER"]
)
def test_onboarding_rejects_malformed_slugs(client: TestClient, bad_slug: str) -> None:
    response = client.post(ONBOARD_PATH, json=_payload(organization_slug=bad_slug))
    assert response.status_code == 422


def test_onboarding_rejects_smuggled_fields(client: TestClient) -> None:
    """`extra="forbid"` must refuse an attempt to set role/status/tenant_id
    directly - the same anti-smuggling posture every other request model
    uses. This is the one unauthenticated write endpoint in the API, so it
    matters most here that a client cannot talk its way into anything but
    an INACTIVE TENANT_ADMIN."""
    response = client.post(ONBOARD_PATH, json=_payload(role="SUPER_ADMIN"))
    assert response.status_code == 422


def test_unverified_admin_cannot_log_in(
    client: TestClient, login: Callable[..., Response]
) -> None:
    onboard = client.post(ONBOARD_PATH, json=_payload())
    assert onboard.status_code == 201

    response = login(
        "acme-onboard", "ada@acme-onboard.com", "correct-horse-battery-staple"
    )
    # The same generic 401 as a wrong password or an unknown user - an
    # unverified account must be indistinguishable from either.
    assert response.status_code == 401


def test_verify_email_activates_the_admin_and_signs_them_in(
    client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        client.post(ONBOARD_PATH, json=_payload())
    token = _token_from_link(_extract_verification_link(caplog))

    response = client.post(VERIFY_PATH, json={"token": token})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    admin = db_session.scalar(select(User).where(User.email == "ada@acme-onboard.com"))
    assert admin is not None
    assert admin.status == UserStatus.ACTIVE.value

    # The now-verified admin can log in normally too.
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "acme-onboard",
            "email": "ada@acme-onboard.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login_response.status_code == 200


def test_verify_email_rejects_an_unknown_token(client: TestClient) -> None:
    response = client.post(VERIFY_PATH, json={"token": "not-a-real-token"})
    assert response.status_code == 401


def test_verify_email_rejects_a_replayed_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        client.post(ONBOARD_PATH, json=_payload())
    token = _token_from_link(_extract_verification_link(caplog))

    first = client.post(VERIFY_PATH, json={"token": token})
    assert first.status_code == 200

    second = client.post(VERIFY_PATH, json={"token": token})
    assert second.status_code == 401


def test_verify_email_rejects_an_expired_token(
    client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """A token that was never consumed but has aged past its TTL must fail
    the same generic way as an unknown or replayed one - not a distinct
    error that would let a caller tell "expired" from "never existed"."""
    with caplog.at_level("INFO"):
        client.post(ONBOARD_PATH, json=_payload())
    token = _token_from_link(_extract_verification_link(caplog))

    admin = db_session.scalar(select(User).where(User.email == "ada@acme-onboard.com"))
    assert admin is not None
    verification = db_session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == admin.id)
    )
    assert verification is not None
    verification.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    response = client.post(VERIFY_PATH, json={"token": token})
    assert response.status_code == 401

    db_session.refresh(admin)
    assert admin.status == UserStatus.INACTIVE.value


def test_verify_email_is_rate_limited_per_ip(client: TestClient) -> None:
    limit = settings.rate_limit_email_verification_per_hour
    for _ in range(limit):
        response = client.post(VERIFY_PATH, json={"token": "not-a-real-token"})
        assert response.status_code == 401

    throttled = client.post(VERIFY_PATH, json={"token": "not-a-real-token"})
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) > 0


def test_resend_verification_issues_a_new_link_that_supersedes_the_old_one(
    client: TestClient, db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        client.post(ONBOARD_PATH, json=_payload())
    old_token = _token_from_link(_extract_verification_link(caplog))

    caplog.clear()
    with caplog.at_level("INFO"):
        response = client.post(
            RESEND_PATH,
            json={"organization_slug": "acme-onboard", "admin_email": "ada@acme-onboard.com"},
        )
    assert response.status_code == 200
    new_token = _token_from_link(_extract_verification_link(caplog))
    assert new_token != old_token

    # The superseded link no longer works...
    assert client.post(VERIFY_PATH, json={"token": old_token}).status_code == 401
    # ...but the fresh one does.
    verify = client.post(VERIFY_PATH, json={"token": new_token})
    assert verify.status_code == 200

    admin = db_session.scalar(select(User).where(User.email == "ada@acme-onboard.com"))
    assert admin is not None
    assert admin.status == UserStatus.ACTIVE.value


def test_resend_verification_is_silent_for_an_unknown_organization(client: TestClient) -> None:
    response = client.post(
        RESEND_PATH,
        json={"organization_slug": "no-such-org", "admin_email": "nobody@example.com"},
    )
    # Same 200, same message as a real account - no enumeration signal.
    assert response.status_code == 200
    assert "sent a new link" in response.json()["message"]


def test_resend_verification_is_silent_for_an_unknown_email(client: TestClient) -> None:
    client.post(ONBOARD_PATH, json=_payload())
    response = client.post(
        RESEND_PATH,
        json={"organization_slug": "acme-onboard", "admin_email": "wrong@acme-onboard.com"},
    )
    assert response.status_code == 200


def test_resend_verification_is_silent_for_an_already_verified_account(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO"):
        client.post(ONBOARD_PATH, json=_payload())
    token = _token_from_link(_extract_verification_link(caplog))
    client.post(VERIFY_PATH, json={"token": token})

    caplog.clear()
    with caplog.at_level("INFO"):
        response = client.post(
            RESEND_PATH,
            json={"organization_slug": "acme-onboard", "admin_email": "ada@acme-onboard.com"},
        )
    assert response.status_code == 200
    # Nothing was actually (re-)sent for an already-active account.
    assert not any(
        getattr(r, "event", None) == "email_not_sent_no_smtp_configured" for r in caplog.records
    )


def test_resend_verification_rejects_smuggled_fields(client: TestClient) -> None:
    response = client.post(
        RESEND_PATH,
        json={
            "organization_slug": "acme-onboard",
            "admin_email": "ada@acme-onboard.com",
            "token": "smuggled",
        },
    )
    assert response.status_code == 422


def test_onboarding_is_rate_limited_per_ip(client: TestClient) -> None:
    limit = settings.rate_limit_onboarding_per_hour
    for index in range(limit):
        response = client.post(
            ONBOARD_PATH,
            json=_payload(
                organization_slug=f"acme-rl-{index}",
                admin_email=f"admin-{index}@acme-rl.com",
            ),
        )
        assert response.status_code == 201, response.text

    throttled = client.post(
        ONBOARD_PATH,
        json=_payload(organization_slug="acme-rl-over", admin_email="over@acme-rl.com"),
    )
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) > 0
