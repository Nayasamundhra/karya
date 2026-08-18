"""Correlation id, access logging and the last-resort 500.

These three belong together: all of them are about being able to say what happened
to one request. Splitting them would mean three ``send`` wrappers computing the
same request id and the same elapsed time.

**Why the 500 lives here.** Starlette's ``ServerErrorMiddleware`` sits *outside*
every application middleware, so an exception handled there produces a response
this middleware never sees - no correlation id header, no access log line, no
structured error record. Catching unhandled exceptions here instead means the one
case an operator most needs to trace is the one case that is fully traced.

The traceback goes to the log and never to the client. That is the whole point of
handling it: the response says ``Internal server error`` and carries the
correlation id, and the operator looks the id up in a log stream that is a trusted
sink.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import (
    bind_request,
    clear_principal,
    new_request_id,
    unbind_request,
)

logger = logging.getLogger(__name__)

#: Header read on the way in and always written on the way out.
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"

#: An inbound id is accepted only if it looks like an id. Client-supplied values
#: end up in the log stream, so an unvalidated one could inject newlines (forging
#: log entries), embed a huge string, or carry data that has no business being
#: retained. Anything that fails this is replaced with a generated id rather than
#: rejected - the caller's tracing preference is not worth failing a request over.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

#: Body returned when an unhandled exception escapes the application. Byte-identical
#: regardless of what went wrong.
_INTERNAL_ERROR_BODY: Final[bytes] = b'{"detail":"Internal server error"}'


def resolve_request_id(scope: Scope) -> str:
    """Take a safe inbound correlation id, or mint one."""
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name == b"x-request-id":
            candidate = raw_value.decode("latin-1", errors="replace")
            if _SAFE_REQUEST_ID.match(candidate):
                return candidate
            break
    return new_request_id()


class RequestContextMiddleware:
    """Assign a correlation id, log one line per request, contain failures."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(scope)
        # A plain dict on the scope, not only a ContextVar: endpoints run in a
        # worker thread whose context is a *copy*, so a principal bound there is
        # invisible to this coroutine. The dict is shared, so it is not.
        state: dict[str, Any] = scope.setdefault("state", {})
        state["request_id"] = request_id

        tokens = bind_request(request_id)
        started = time.perf_counter()
        response_started = False
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            elapsed_ms = self._elapsed_ms(started)
            logger.exception(
                "unhandled_exception",
                extra={
                    "event": "unhandled_exception",
                    **self._request_fields(scope, state),
                    "duration_ms": elapsed_ms,
                },
            )
            if response_started:
                # Headers are already on the wire; there is no valid response left
                # to send. Let the server tear the connection down.
                unbind_request(tokens)
                clear_principal()
                raise
            status_code = 500
            await self._send_internal_error(send, request_id)
            self._log_access(scope, state, status_code, elapsed_ms)
            unbind_request(tokens)
            clear_principal()
            return

        self._log_access(scope, state, status_code, self._elapsed_ms(started))
        unbind_request(tokens)
        clear_principal()

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 2)

    @staticmethod
    async def _send_internal_error(send: Send, request_id: str) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_INTERNAL_ERROR_BODY)).encode()),
                    (REQUEST_ID_HEADER.lower().encode(), request_id.encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _INTERNAL_ERROR_BODY})

    @staticmethod
    def _request_fields(scope: Scope, state: dict[str, Any]) -> dict[str, Any]:
        """The fields describing a request, with nothing sensitive in them.

        ``path`` is logged; the **query string is not**. A path carries route
        structure and identifiers, which is exactly what an operator needs. A
        query string carries user input - ``?search=<someone's name>`` - which has
        no place in a log line that may be retained for months.

        ``route`` is the matched template (``/api/v1/users/{user_id}``), which is
        what makes per-endpoint aggregation possible without the identifier
        exploding the cardinality.
        """
        route = scope.get("route")
        fields: dict[str, Any] = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "route": getattr(route, "path", None),
            "client_ip": scope["client"][0] if scope.get("client") else None,
        }
        # Set by the authentication dependency once identity is verified against
        # the database, so this can never be a value the caller supplied.
        principal = state.get("principal")
        if principal:
            fields["user_id"] = principal.get("user_id")
            fields["tenant_id"] = principal.get("tenant_id")
        return fields

    def _log_access(
        self,
        scope: Scope,
        state: dict[str, Any],
        status_code: int,
        duration_ms: float,
    ) -> None:
        # 5xx is a defect, 4xx is a rejected caller, everything else is routine.
        level = (
            logging.ERROR
            if status_code >= 500
            else logging.WARNING
            if status_code >= 400
            else logging.INFO
        )
        logger.log(
            level,
            "http_request",
            extra={
                "event": "http_request",
                **self._request_fields(scope, state),
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
