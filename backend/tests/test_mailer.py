"""`app.services.email.mailer.send_email`'s real transports (Phase 11 SMTP,
Phase 11-follow-up Brevo HTTP API).

`test_onboarding.py` exercises this module too, but only ever through the
*unconfigured* branch (neither transport set, so the email is logged instead
of sent) - that's the only path a bare local checkout or the rest of the
suite needs. This module covers the other two branches: an actual
`smtplib.SMTP` connect/STARTTLS/login/send, and an actual HTTPS POST to
Brevo's API, each translating a failure into `EmailDeliveryError` - with
`smtplib.SMTP` / `urllib.request.urlopen` mocked throughout, so neither needs
real network access or credentials.
"""

from __future__ import annotations

import json
import urllib.error
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


def _brevo_configured(**overrides: object) -> Settings:
    """A `Settings` with Brevo's HTTP API configured instead of SMTP."""
    base: dict[str, object] = {
        "brevo_api_key": SecretStr("a-test-brevo-api-key"),
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


# ---------------------------------------------------------------------------
# Brevo HTTP API transport
#
# Added after a real send attempt from Render (where Karya is actually
# deployed) confirmed its free tier blocks outbound SMTP entirely - the
# connection to smtp-relay.brevo.com hung until smtplib's own timeout and
# never completed. This is the transport that actually works there.
# ---------------------------------------------------------------------------


def _mock_urlopen_success() -> MagicMock:
    response = MagicMock()
    response.read.return_value = b'{"messageId": "abc123"}'
    context_manager = MagicMock()
    context_manager.__enter__.return_value = response
    return context_manager


def test_brevo_api_send_posts_the_expected_request() -> None:
    config = _brevo_configured()

    with patch("urllib.request.urlopen", return_value=_mock_urlopen_success()) as mock_urlopen:
        send_email(to="admin@acme.com", subject="Verify your Karya account", body="link", config=config)

    mock_urlopen.assert_called_once()
    request = mock_urlopen.call_args[0][0]
    assert request.full_url == "https://api.brevo.com/v3/smtp/email"
    assert request.get_header("Api-key") == "a-test-brevo-api-key"
    assert request.get_header("Content-type") == "application/json"
    payload = json.loads(request.data)
    assert payload["sender"] == {"email": "bot@example.com"}
    assert payload["to"] == [{"email": "admin@acme.com"}]
    assert payload["subject"] == "Verify your Karya account"
    assert payload["textContent"] == "link"


def test_brevo_is_preferred_when_both_transports_are_configured() -> None:
    """SMTP is what a developer might configure locally for a non-Brevo
    provider; Brevo's API is the one known to work on the platform Karya
    actually runs on (see the module docstring) - so when both happen to be
    set, Brevo wins rather than either being an error.
    """
    config = _configured(brevo_api_key="a-test-brevo-api-key")

    with patch("urllib.request.urlopen", return_value=_mock_urlopen_success()) as mock_urlopen:
        with patch("smtplib.SMTP") as mock_smtp_cls:
            send_email(to="admin@acme.com", subject="s", body="b", config=config)

    mock_urlopen.assert_called_once()
    mock_smtp_cls.assert_not_called()


def test_a_brevo_http_error_raises_email_delivery_error() -> None:
    """A 4xx/5xx from Brevo (bad key, rejected sender, rate limited, ...)
    must not reach the caller as a raw exception - only as
    `EmailDeliveryError`, same contract as the SMTP transport.
    """
    config = _brevo_configured()
    http_error = urllib.error.HTTPError(
        "https://api.brevo.com/v3/smtp/email", 401, "Unauthorized", {}, None
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(EmailDeliveryError):
            send_email(to="admin@acme.com", subject="s", body="b", config=config)


def test_a_brevo_connection_failure_raises_email_delivery_error() -> None:
    """The exact failure mode observed against the real deployment: the
    connection never completes and eventually times out.
    """
    config = _brevo_configured()

    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        with pytest.raises(EmailDeliveryError):
            send_email(to="admin@acme.com", subject="s", body="b", config=config)


def test_brevo_body_and_recipient_are_never_logged_once_configured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _brevo_configured()

    with patch("urllib.request.urlopen", return_value=_mock_urlopen_success()):
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


def test_a_brevo_http_error_never_logs_the_response_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Brevo's own error responses can echo the request back, recipient
    address included - the log must carry only the status code, not
    anything read from the response (see the mailer module).
    """
    config = _brevo_configured()
    http_error = urllib.error.HTTPError(
        "https://api.brevo.com/v3/smtp/email",
        400,
        "Bad Request",
        {},
        None,
    )

    with patch("urllib.request.urlopen", side_effect=http_error):
        with caplog.at_level("ERROR"):
            with pytest.raises(EmailDeliveryError):
                send_email(to="admin@acme.com", subject="s", body="b", config=config)

    record = next(r for r in caplog.records if r.message == "email_delivery_failed")
    assert record.status_code == 400
    assert "admin@acme.com" not in record.getMessage()
