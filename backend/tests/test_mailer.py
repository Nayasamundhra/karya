"""`app.services.email.mailer.send_email`'s real-SMTP path (Phase 11).

`test_onboarding.py` exercises this module too, but only ever through the
*unconfigured* branch (SMTP_HOST unset, so the email is logged instead of
sent) - that's the only path a bare local checkout or the rest of the suite
needs. This module covers the other branch: an actual `smtplib.SMTP`
connect/STARTTLS/login/send, and translating a failure into
`EmailDeliveryError` - with `smtplib.SMTP` mocked throughout, so it needs no
real network access or credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.email.mailer import EmailDeliveryError, send_email


def _configured(**overrides: object) -> Settings:
    """A `Settings` with SMTP configured, built without reading `.env` -
    a real developer's SMTP credentials in `.env` must never leak into what
    this test asserts was sent.
    """
    base: dict[str, object] = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "bot@example.com",
        "smtp_password": SecretStr("a-test-app-password"),
        "smtp_from_address": "bot@example.com",
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def test_a_configured_send_connects_authenticates_and_sends() -> None:
    config = _configured()

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        send_email(to="admin@acme.com", subject="Verify your Karya account", body="link", config=config)

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=config.smtp_timeout_seconds)
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("bot@example.com", "a-test-app-password")
    mock_smtp.send_message.assert_called_once()
    sent_message = mock_smtp.send_message.call_args[0][0]
    assert sent_message["To"] == "admin@acme.com"
    assert sent_message["From"] == "bot@example.com"
    assert sent_message["Subject"] == "Verify your Karya account"
    assert sent_message.get_content().strip() == "link"


def test_smtp_use_tls_false_skips_starttls() -> None:
    config = _configured(smtp_use_tls=False)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        send_email(to="admin@acme.com", subject="s", body="b", config=config)

    mock_smtp.starttls.assert_not_called()


def test_no_username_or_password_skips_login() -> None:
    config = _configured(smtp_username=None, smtp_password=None)

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        send_email(to="admin@acme.com", subject="s", body="b", config=config)

    mock_smtp.login.assert_not_called()
    mock_smtp.send_message.assert_called_once()


def test_a_connection_failure_raises_email_delivery_error() -> None:
    """`OSError` (e.g. connection refused, DNS failure) must not reach the
    caller as a raw exception - only as `EmailDeliveryError`, which routes
    translate into a clean 503 rather than a raw traceback (see
    `app/api/v1/onboarding.py`).
    """
    config = _configured()

    with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("Connection refused")):
        with pytest.raises(EmailDeliveryError):
            send_email(to="admin@acme.com", subject="s", body="b", config=config)


def test_an_smtp_auth_failure_raises_email_delivery_error() -> None:
    import smtplib

    config = _configured()

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        with pytest.raises(EmailDeliveryError):
            send_email(to="admin@acme.com", subject="s", body="b", config=config)


def test_the_body_and_recipient_are_never_logged_once_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only the *unconfigured* fallback logs the body (see the module
    docstring) - once real SMTP is set up, a successful send logs only the
    subject, and a failed one adds only the exception class name and host.
    """
    config = _configured()

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

        with caplog.at_level("INFO"):
            send_email(
                to="admin@acme.com",
                subject="Verify your Karya account",
                body="http://example.com/verify?token=super-secret",
                config=config,
            )

    for record in caplog.records:
        assert "admin@acme.com" not in record.getMessage()
        assert "super-secret" not in record.getMessage()
        assert getattr(record, "to", None) is None
        assert getattr(record, "body", None) is None
