"""Per-request context, carried out of band so nothing has to thread it through.

A request id is only useful if it appears on *every* log line the request
produced - including lines written deep inside a service that has no idea an HTTP
request exists. Passing it down through every function signature would be
invasive and would be forgotten somewhere, so it lives in :mod:`contextvars` and
is attached to log records by :class:`RequestContextFilter`.

``contextvars`` is the right tool rather than a thread-local: Karya's endpoints
are sync functions that Starlette runs in a worker thread, and a ``ContextVar``
set in the ASGI coroutine is visible to that thread because Starlette copies the
context when it dispatches. A thread-local set in the event loop would not be.

Only non-sensitive identifiers are stored. There is deliberately no slot for a
token, a password or a nonce.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

#: Correlation id for the request currently being handled, if any.
_request_id: ContextVar[str | None] = ContextVar("karya_request_id", default=None)
#: Authenticated user, once :func:`app.api.deps.get_current_user` has resolved it.
_user_id: ContextVar[str | None] = ContextVar("karya_user_id", default=None)
#: Tenant of the authenticated user. Safe to log: it identifies a customer
#: organisation, not a person, and it is the field an operator filters by first.
_tenant_id: ContextVar[str | None] = ContextVar("karya_tenant_id", default=None)


@dataclass(frozen=True, slots=True)
class ContextTokens:
    """Reset handles returned by :func:`bind_request`.

    Held so the middleware can restore the previous values instead of clearing
    them outright - clearing would corrupt an outer context if this code is ever
    nested (for example a test harness that binds a context of its own).
    """

    request_id: Token[str | None]


def new_request_id() -> str:
    """Generate a fresh correlation id."""
    return uuid.uuid4().hex


def bind_request(request_id: str) -> ContextTokens:
    """Enter a request context and return the handles needed to leave it."""
    return ContextTokens(request_id=_request_id.set(request_id))


def unbind_request(tokens: ContextTokens) -> None:
    """Leave the request context, restoring whatever was there before."""
    _request_id.reset(tokens.request_id)


def get_request_id() -> str | None:
    """The current request's correlation id, or ``None`` outside a request."""
    return _request_id.get()


def bind_principal(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Record who the authenticated caller is, for log correlation only.

    Called from the authentication dependency once identity has been *verified*
    against the database. Never called with a value taken from the request, so a
    log line attributing an action to a user cannot be forged by a client.
    """
    _user_id.set(str(user_id))
    _tenant_id.set(str(tenant_id))


def clear_principal() -> None:
    """Forget the authenticated caller.

    Called when a request context ends. Endpoints run in a pooled worker thread
    whose context is a copy, but the copy is made per dispatch, so this exists to
    keep a long-lived non-request context (a test, a script) from inheriting a
    stale principal.
    """
    _user_id.set(None)
    _tenant_id.set(None)


class RequestContextFilter(logging.Filter):
    """Attach the current request context to every log record.

    A filter rather than a formatter concern: this way the fields are present on
    the record itself, so *any* handler or formatter - JSON, console, or one added
    later - sees them without repeating the lookup.

    An explicit ``extra=`` always wins. That matters for the access log, which is
    emitted from the ASGI coroutine: an endpoint runs in a worker thread whose
    context is a copy, so a principal bound there is not visible here, and the
    access-log middleware passes it explicitly instead. Overwriting it with the
    (empty) context value would throw away the better answer.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for name, variable in (
            ("request_id", _request_id),
            ("user_id", _user_id),
            ("tenant_id", _tenant_id),
        ):
            if getattr(record, name, None) is None:
                setattr(record, name, variable.get())
        return True
