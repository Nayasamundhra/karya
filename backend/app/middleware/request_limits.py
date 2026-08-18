"""Request size limits, enforced before anything is parsed.

Pydantic validates the *shape* of a request. It cannot help with the size of one,
because by the time a schema is applied the body has already been received and
JSON-decoded - which is where a multi-megabyte payload costs memory and CPU. So
size is checked here, at the ASGI boundary, ahead of routing and validation.

Two checks:

* **Body size.** ``Content-Length`` is rejected outright when it exceeds the
  limit, so an oversized upload is refused after its headers and before its body.
  A request that declares no length (chunked transfer encoding) cannot be
  pre-judged, so its body is counted as it streams and the request is failed the
  moment the limit is passed. Trusting ``Content-Length`` alone would be a hole: a
  client is free to omit it.
* **Query string size.** A pathological URL is cheap to send and, unlike a body,
  ends up in server access logs and proxy caches. The limit is generous next to
  Karya's longest legitimate query (a date range plus pagination plus a 255-character
  search term).

Neither replaces or relaxes any existing validation: a request that passes these
still faces the same schemas, the same ``extra="forbid"``, and the same pagination
and range caps as before.
"""

from __future__ import annotations

from typing import Final

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, settings

_BODY_TOO_LARGE_DETAIL: Final[str] = "Request body too large"
_BODY_TOO_LARGE_BODY: Final[bytes] = b'{"detail":"Request body too large"}'
_QUERY_TOO_LONG_BODY: Final[bytes] = b'{"detail":"Query string too long"}'

_STATUS_PAYLOAD_TOO_LARGE: Final[int] = 413
_STATUS_URI_TOO_LONG: Final[int] = 414


class BodyTooLargeError(HTTPException):
    """Raised from the wrapped ``receive`` when a streamed body exceeds the limit.

    An ``HTTPException`` rather than a bare exception, because of where it surfaces:
    the body is read inside FastAPI's parameter solving, which wraps *any* unexpected
    exception into ``400 There was an error parsing the body``. It re-raises an
    ``HTTPException`` untouched - explicitly, for this case - so subclassing is what
    makes the status 413 instead of a misleading 400.

    The middleware also catches it, for the paths where FastAPI is not the one
    reading the body. Both routes produce the same response.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=_STATUS_PAYLOAD_TOO_LARGE, detail=_BODY_TOO_LARGE_DETAIL
        )


async def _send_error(send: Send, status_code: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestLimitsMiddleware:
    """Reject requests whose body or query string is larger than configured."""

    def __init__(self, app: ASGIApp, config: Settings | None = None) -> None:
        self.app = app
        self.config = config or settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if len(scope.get("query_string", b"")) > self.config.max_query_string_bytes:
            await _send_error(send, _STATUS_URI_TOO_LONG, _QUERY_TOO_LONG_BODY)
            return

        limit = self.config.max_request_body_bytes
        declared = self._declared_length(scope)
        if declared is not None and declared > limit:
            await _send_error(send, _STATUS_PAYLOAD_TOO_LARGE, _BODY_TOO_LARGE_BODY)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, self._counting_receive(receive, limit), send_wrapper)
        except BodyTooLargeError:
            if response_started:  # pragma: no cover - a handler cannot respond
                raise  # before reading the body it rejected.
            await _send_error(send, _STATUS_PAYLOAD_TOO_LARGE, _BODY_TOO_LARGE_BODY)

    @staticmethod
    def _declared_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", ()):
            if name == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    # A malformed Content-Length is the server's problem to
                    # reject, not something to guess at here.
                    return None
        return None

    @staticmethod
    def _counting_receive(receive: Receive, limit: int) -> Receive:
        """Wrap ``receive`` so a streamed body cannot exceed ``limit``."""
        received = 0

        async def counting() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLargeError()
            return message

        return counting
