"""Outbound transactional email.

Karya sends exactly one kind of email today: the onboarding verification
link. Two transports, both stdlib-only (no third-party dependency, the same
precedent Phase 7 set for logging/rate-limiting/security headers - "don't
reach for a package for something the standard library already does"):

* SMTP (`smtplib`), the original Phase 11 transport - works on any host that
  allows outbound SMTP.
* Brevo's HTTP transactional-email API (`urllib.request`, a plain HTTPS
  POST) - added because Render's free tier, where Karya is actually
  deployed, blocks outbound SMTP connections as an anti-spam-relay measure
  (confirmed directly: a real send attempt from Render hung until
  `smtplib`'s own timeout and failed with `TimeoutError`, never reaching
  `smtp-relay.brevo.com` at all). HTTPS is not blocked the way SMTP ports
  are, so this is the transport that actually works there.

If `BREVO_API_KEY` is set, it is preferred over SMTP even when both happen to
be configured - it is the one known to work on the platform this runs on. If
neither is set, sending degrades to a structured log line instead of
raising - the same fallback other optional-in-development features already
use (rate limiting can be disabled, docs can be disabled). A fresh local
checkout and the test suite need no mail server or API key configured at
all; a real deployment that forgets to configure either finds out from its
own logs rather than every onboarding attempt failing with a 500.
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

#: Brevo's transactional-email endpoint. Not configurable - Brevo is a
#: specific provider choice, not a generic "any HTTP mail API" abstraction;
#: a second HTTP-based provider would be a new transport, not a new URL.
_BREVO_SEND_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    """A transport is configured but the send itself failed.

    Deliberately distinct from "no transport is configured" (which is not
    an error - see the module docstring). A caller that lets this propagate
    gets a real transaction rollback rather than a signup left half-created
    with a verification link nobody received; a route should translate it
    into a clean 5xx rather than let a raw exception/traceback reach the
    client.
    """


def send_email(
    *, to: str, subject: str, body: str, config: Settings | None = None
) -> None:
    """Send one plain-text email, or log it in full as a dev-mode fallback.

    Once a real transport is configured, this never logs the recipient
    address or the body: the backend's own conventions already keep raw
    email addresses out of logs (see `backend/README.md` on failed-login
    logging), and the body may contain a one-time link that grants account
    access - it has no business persisting wherever INFO-level logs end up
    shipped.

    The *unconfigured* branch below is the one deliberate exception: with no
    transport configured, this log line is the only delivery mechanism there
    is, so it must carry the body (link included) or onboarding is simply
    undeliverable locally. That trade only exists while nothing is
    configured - setting BREVO_API_KEY or SMTP_HOST removes this branch and
    its logging entirely.
    """
    config = config or settings

    if config.brevo_api_key:
        _send_via_brevo_api(to=to, subject=subject, body=body, config=config)
        return

    if config.smtp_host:
        _send_via_smtp(to=to, subject=subject, body=body, config=config)
        return

    logger.info(
        "email_not_sent_no_smtp_configured",
        extra={
            "event": "email_not_sent_no_smtp_configured",
            "subject": subject,
            "to": to,
            "body": body,
        },
    )


def _send_via_smtp(*, to: str, subject: str, body: str, config: Settings) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.smtp_from_address
    message["To"] = to
    message.set_content(body)

    try:
        with smtplib.SMTP(
            config.smtp_host, config.smtp_port, timeout=config.smtp_timeout_seconds
        ) as smtp:
            if config.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if config.smtp_username and config.smtp_password:
                smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        # Never the recipient address or body here either - only what's
        # needed to diagnose a delivery failure from the logs.
        logger.error(
            "email_delivery_failed",
            extra={
                "event": "email_delivery_failed",
                "transport": "smtp",
                "subject": subject,
                "smtp_host": config.smtp_host,
                "error": type(exc).__name__,
            },
        )
        raise EmailDeliveryError(str(exc)) from exc

    logger.info(
        "email_sent", extra={"event": "email_sent", "transport": "smtp", "subject": subject}
    )


def _send_via_brevo_api(*, to: str, subject: str, body: str, config: Settings) -> None:
    """Send via Brevo's HTTP API - see the module docstring for why this
    exists alongside SMTP rather than replacing it.

    Plain `urllib.request` rather than a third-party HTTP client: this is
    one POST with a JSON body and one auth header, well within what the
    standard library does comfortably, and `httpx` (already a dependency,
    but a test-only one - see `pyproject.toml`) is deliberately not promoted
    to a runtime dependency just for this.
    """
    payload = json.dumps(
        {
            "sender": {"email": config.smtp_from_address},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        _BREVO_SEND_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "api-key": config.brevo_api_key.get_secret_value(),  # type: ignore[union-attr]
            "content-type": "application/json",
            "accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(
            request, timeout=config.brevo_api_timeout_seconds
        ) as response:
            # A non-2xx status raises HTTPError before this line is reached
            # (urllib's default behaviour); reading the body here is just to
            # complete the request cleanly, not because the response is used.
            response.read()
    except urllib.error.HTTPError as exc:
        # Never the response body: on a validation failure Brevo's API
        # echoes the request back, recipient address included, which is
        # exactly what `EmailDeliveryError`'s docstring says must not reach
        # a log. The status code alone is enough to diagnose from.
        logger.error(
            "email_delivery_failed",
            extra={
                "event": "email_delivery_failed",
                "transport": "brevo_api",
                "subject": subject,
                "error": type(exc).__name__,
                "status_code": exc.code,
            },
        )
        raise EmailDeliveryError(f"Brevo API returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        logger.error(
            "email_delivery_failed",
            extra={
                "event": "email_delivery_failed",
                "transport": "brevo_api",
                "subject": subject,
                "error": type(exc).__name__,
            },
        )
        raise EmailDeliveryError(str(exc)) from exc

    logger.info(
        "email_sent",
        extra={"event": "email_sent", "transport": "brevo_api", "subject": subject},
    )
