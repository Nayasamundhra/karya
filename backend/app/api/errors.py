"""Application-wide exception handling.

Karya's error contract is one shape everywhere: ``{"detail": ...}``, with the
correlation id in the ``X-Request-ID`` response header rather than in the body.
Keeping the id out of the body matters - it means the envelope is byte-identical
for two callers who hit the same error, so no test, cache or client has to special-case
a varying field, and the anti-enumeration guarantees from Phases 2-6 (a
cross-tenant id must be indistinguishable from a fictional one) survive unchanged.

Three handlers are registered. Everything else already produces the right thing:
``HTTPException`` is FastAPI's own handler, which emits ``{"detail": ...}`` and
preserves headers such as ``WWW-Authenticate`` and ``Retry-After``, so it is left
alone.

**Unhandled exceptions** are not handled here. They are caught by
:class:`~app.middleware.request_context.RequestContextMiddleware`, which sits
outside Starlette's ``ServerErrorMiddleware`` and can therefore attach the
correlation id and an access-log line to the failure. See that module for why.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

#: The only keys copied out of a Pydantic validation error.
#:
#: Pydantic also supplies ``input`` (the offending value), ``ctx`` (constraint
#: details) and ``url`` (a link to its docs). ``input`` is the dangerous one: for a
#: password that fails the length check it is **the password**, which FastAPI's
#: default handler echoes straight back in the 422 body. That is a credential in a
#: response body, and from there in a browser console, a client-side error report
#: or a proxy log. ``ctx`` can carry the same value for other error types, and
#: ``url`` is noise. So the response is built from an allowlist rather than by
#: removing known-bad keys - a new Pydantic error field cannot leak by default.
_SAFE_VALIDATION_KEYS: Final[tuple[str, ...]] = ("type", "loc", "msg")

_INTERNAL_ERROR = "Internal server error"


def sanitise_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    """Reduce Pydantic validation errors to their non-sensitive fields.

    The result still tells a client exactly what to fix - which field, and why -
    because ``loc`` names the field and ``msg`` states the rule. What it no longer
    does is quote the value back.
    """
    sanitised: list[dict[str, Any]] = []
    for error in errors:
        if not isinstance(error, dict):  # pragma: no cover - defensive
            continue
        entry = {key: error[key] for key in _SAFE_VALIDATION_KEYS if key in error}
        # `loc` may contain ints (list indices); str() would misrepresent them, so
        # values are passed through and JSON-encoded as they are.
        sanitised.append(entry)
    return sanitised


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answer 422 without echoing the submitted values back."""
    return JSONResponse(
        status_code=422,
        content={"detail": sanitise_validation_errors(list(exc.errors()))},
    )


async def database_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Answer 500 for a database failure, saying nothing about the database.

    A ``SQLAlchemyError``'s string form can contain the SQL statement, the table
    and constraint names, and - for some drivers - the bound parameters. None of
    that belongs in a response. The full exception goes to the log with the
    correlation id attached, which is where an operator should be looking anyway.

    Note this is a *last resort*. Expected conflicts are already translated much
    closer to the action that caused them: Phase 6 catches the unique-violation
    inside a savepoint and returns a clean 409. Reaching this handler means
    something genuinely unforeseen happened.
    """
    logger.exception(
        "database_error",
        extra={"event": "database_error", "error_type": type(exc).__name__},
    )
    return JSONResponse(status_code=500, content={"detail": _INTERNAL_ERROR})


def register_exception_handlers(app: FastAPI) -> None:
    """Install Karya's exception handlers on ``app``.

    The ignores are Starlette's signature being intentionally wide
    (``Callable[[Request, Exception], Response]``) while each handler above is
    narrowed to the exception it actually handles - which is the safer direction to
    be wrong in.
    """
    app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,  # type: ignore[arg-type]
    )
    app.add_exception_handler(
        SQLAlchemyError,
        database_exception_handler,  # type: ignore[arg-type]
    )
