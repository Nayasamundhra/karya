"""Structured application logging.

Karya logs **events with fields**, not sentences with values interpolated into
them. ``logger.info("login_failed", extra={"event": "login_failed", ...})`` can be
filtered, counted and alerted on; ``logger.info(f"login failed for {email}")``
cannot, and it puts a personal identifier into a string nobody can redact later.

Two safety properties are enforced here rather than left to the caller:

* **Key-based redaction.** Any field whose name suggests a credential
  (``password``, ``token``, ``secret``, ``nonce``, ``authorization``, ...) is
  replaced with ``[redacted]`` before it is serialised. Nothing in Karya passes
  such a field deliberately - this is the net under the tightrope, so that one
  careless ``extra=`` in a future phase cannot put a secret in the log stream.
* **Automatic correlation.** :class:`~app.core.context.RequestContextFilter`
  attaches ``request_id``/``user_id``/``tenant_id`` to every record, so a service
  deep in the call stack does not have to know or care about them.

Logging is configured once at startup (see the application lifespan) rather than
at import time, so importing ``app.*`` in a script or a test does not hijack that
process's logging setup.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Final

from app.core.config import LogFormat, Settings, settings
from app.core.context import RequestContextFilter

#: Substrings that mark a field name as sensitive. Matched case-insensitively
#: against the whole key, so ``new_password``, ``refresh_token`` and
#: ``Authorization`` are all caught.
SENSITIVE_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "credential",
    "nonce",
    "api_key",
    "apikey",
    "cookie",
    "hash",
)

#: Placeholder substituted for a redacted value.
REDACTED: Final[str] = "[redacted]"

#: How deep to walk into nested mappings when redacting. Log payloads are flat by
#: convention; this exists so a nested dict cannot smuggle a credential past the
#: check, without turning every log call into an unbounded tree walk.
_MAX_REDACTION_DEPTH: Final[int] = 3

#: Attributes ``logging`` puts on every record. Anything else on a record came
#: from an ``extra=`` and is therefore part of the structured payload.
_STANDARD_RECORD_ATTRS: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

#: Context fields promoted to top-level keys in the rendered record.
_CONTEXT_ATTRS: Final[tuple[str, ...]] = ("request_id", "user_id", "tenant_id")

#: Loggers whose output is routed through our handler instead of their own, so a
#: deployment reads one uniform stream. ``uvicorn.access`` is silenced because
#: Karya emits its own richer access line, which logs the matched *route
#: template* rather than the raw path - a raw path can carry a search term or an
#: identifier, and a duplicate line per request buries the signal.
_UVICORN_LOGGERS: Final[tuple[str, ...]] = ("uvicorn", "uvicorn.error")
_UVICORN_ACCESS_LOGGER: Final[str] = "uvicorn.access"


def redact(value: Any, *, depth: int = 0) -> Any:
    """Return ``value`` with sensitively-named keys replaced.

    Only *names* are inspected; values are never pattern-matched. Scanning values
    for things that look like secrets is both expensive and unreliable, and a
    codebase that never passes a secret does not need it.
    """
    if depth >= _MAX_REDACTION_DEPTH or not isinstance(value, dict):
        return value
    cleaned: dict[Any, Any] = {}
    for key, item in value.items():
        if isinstance(key, str) and is_sensitive_key(key):
            cleaned[key] = REDACTED
        else:
            cleaned[key] = redact(item, depth=depth + 1)
    return cleaned


def is_sensitive_key(key: str) -> bool:
    """Whether a field name suggests it holds a credential."""
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def record_payload(record: logging.LogRecord) -> dict[str, Any]:
    """Build the structured payload for one log record.

    Shared by both formatters so JSON and console output can never disagree about
    what a record contains.
    """
    payload: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    for attribute in _CONTEXT_ATTRS:
        value = getattr(record, attribute, None)
        if value is not None:
            payload[attribute] = value

    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_ATTRS or key in _CONTEXT_ATTRS:
            continue
        if key.startswith("_"):
            continue
        payload[key] = REDACTED if is_sensitive_key(key) else redact(value)

    if record.exc_info:
        # The traceback goes to the log, which is a trusted sink - never to an
        # HTTP response. See app/api/errors.py.
        payload["exception"] = logging.Formatter().formatException(record.exc_info)
    if record.stack_info:
        payload["stack"] = record.stack_info
    return payload


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        # default=str so an unexpected object (a UUID, a datetime, an enum)
        # degrades to its string form instead of losing the whole log line.
        return json.dumps(record_payload(record), default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Human-readable single line, for development."""

    def format(self, record: logging.LogRecord) -> str:
        payload = record_payload(record)
        head = (
            f"{payload.pop('timestamp')} {payload.pop('level'):<8}"
            f" {payload.pop('logger')} | {payload.pop('message')}"
        )
        exception = payload.pop("exception", None)
        fields = " ".join(f"{key}={value!r}" for key, value in payload.items())
        line = f"{head}  {fields}".rstrip()
        return f"{line}\n{exception}" if exception else line


def build_handler(config: Settings) -> logging.Handler:
    """Create the single stderr handler used by the whole process.

    stderr rather than stdout so application logs stay separable from anything a
    process writes to stdout, and because container runtimes capture both.
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        JsonFormatter() if config.log_format is LogFormat.JSON else ConsoleFormatter()
    )
    handler.addFilter(RequestContextFilter())
    return handler


#: Set once :func:`configure_logging` has taken effect in this process.
_configured = False


def configure_logging(config: Settings | None = None, *, force: bool = False) -> None:
    """Install Karya's logging configuration on the root logger.

    Called from the application lifespan, which may run many times in one process
    (a reloader, or a test suite that starts hundreds of application instances).
    So it applies **once** unless ``force`` is passed: repeatedly tearing down the
    root handlers would fight with whatever else owns logging in that process -
    pytest's capture, for one - for no benefit.
    """
    global _configured
    if _configured and not force:
        return
    config = config or settings

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(build_handler(config))
    root.setLevel(config.log_level_number)

    # Let uvicorn's own loggers flow into the handler above instead of writing
    # their default plain-text lines alongside ours.
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    access = logging.getLogger(_UVICORN_ACCESS_LOGGER)
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    # SQLAlchemy is quiet by default (echo=False) but its pool and dialect
    # loggers become extremely chatty at DEBUG, which is the level someone
    # reaches for when debugging their own code, not the ORM's.
    logging.getLogger("sqlalchemy.engine").setLevel(
        max(config.log_level_number, logging.WARNING)
    )
    # httpx logs one INFO line per request it makes. Karya makes none in
    # production, but the test client does, and those lines duplicate our own
    # access log with less information in them.
    logging.getLogger("httpx").setLevel(
        max(config.log_level_number, logging.WARNING)
    )
    _configured = True
