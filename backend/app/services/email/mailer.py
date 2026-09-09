"""Outbound transactional email.

Karya sends exactly one kind of email today: the onboarding verification
link. This is deliberately minimal - stdlib `smtplib`, no third-party
dependency, the same precedent Phase 7 set for logging/rate-limiting/security
headers ("don't reach for a package for something the standard library
already does").

If `SMTP_HOST` is unset, sending degrades to a structured log line instead of
raising - the same fallback other optional-in-development features already
use (rate limiting can be disabled, docs can be disabled). A fresh local
checkout and the test suite need no mail server configured at all; a real
deployment that forgets to configure one finds out from its own logs rather
than every onboarding attempt failing with a 500.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """SMTP is configured but the send itself failed (network, auth, timeout).

    Deliberately distinct from "SMTP is unconfigured" (which is not an
    error - see the module docstring). A caller that lets this propagate
    gets a real transaction rollback rather than a signup left half-created
    with a verification link nobody received; a route should translate it
    into a clean 5xx rather than let a raw `smtplib`/`OSError` traceback
    reach the client.
    """


def send_email(
    *, to: str, subject: str, body: str, config: Settings | None = None
) -> None:
    """Send one plain-text email, or log it in full as a dev-mode fallback.

    Once real SMTP is configured, this never logs the recipient address or
    the body: the backend's own conventions already keep raw email addresses
    out of logs (see `backend/README.md` on failed-login logging), and the
    body may contain a one-time link that grants account access - it has no
    business persisting wherever INFO-level logs end up shipped.

    The *unconfigured* branch below is the one deliberate exception: with no
    SMTP host set, this log line is the only delivery mechanism there is, so
    it must carry the body (link included) or onboarding is simply
    undeliverable locally. That trade only exists while SMTP is unconfigured
    - filling in SMTP_HOST removes this branch and its logging entirely.
    """
    config = config or settings

    if not config.smtp_host:
        logger.info(
            "email_not_sent_no_smtp_configured",
            extra={
                "event": "email_not_sent_no_smtp_configured",
                "subject": subject,
                "to": to,
                "body": body,
            },
        )
        return

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
                "subject": subject,
                "smtp_host": config.smtp_host,
                "error": type(exc).__name__,
            },
        )
        raise EmailDeliveryError(str(exc)) from exc

    logger.info("email_sent", extra={"event": "email_sent", "subject": subject})
