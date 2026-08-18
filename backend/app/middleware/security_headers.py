"""Response security headers.

Karya is a JSON API, not a website, which changes which headers are worth setting
and why. Each one below is here for a stated reason; none is cargo-cult.

============================== ==============================================
Header                         Why Karya sets it
============================== ==============================================
``X-Content-Type-Options``     A JSON response containing attacker-influenced
                               text (a name, a search term echoed in an error)
                               must never be sniffed as HTML and executed.
                               ``nosniff`` makes the declared content type
                               binding.
``Referrer-Policy``            Karya's URLs contain user and tenant UUIDs. Without
                               this, a browser navigating away can leak the full
                               URL - identifiers included - to a third-party site
                               in the ``Referer`` header.
``X-Frame-Options`` +          Framing an API response is not directly dangerous,
``frame-ancestors 'none'``     but ``/docs`` is a real HTML page and framing it is
                               a clickjacking surface. Both are sent because
                               ``frame-ancestors`` is the modern control and
                               ``X-Frame-Options`` is what older browsers honour.
``Content-Security-Policy``    Turns "this response is data" into something the
                               browser enforces: an API response may load nothing,
                               execute nothing and be framed by nothing. A
                               relaxed policy is used for the docs pages, which
                               genuinely are documents - see below.
``Cache-Control: no-store``    Every API response is either authenticated or an
                               error. A shared cache or a browser's disk cache
                               holding one user's attendance history is a real
                               leak, and ``no-store`` is the only directive that
                               forbids writing it down at all.
``Strict-Transport-Security``  Only when configured (production by default).
                               Meaningful solely over HTTPS, and actively harmful
                               on ``localhost``, where it would pin a developer's
                               whole browser profile to a scheme that host cannot
                               serve.
============================== ==============================================

Deliberately **not** set: ``X-XSS-Protection`` (removed from every current
browser, and it introduced vulnerabilities of its own), ``Cross-Origin-*``
isolation headers (they govern document contexts, which an API has none of), and
``Permissions-Policy`` (it constrains browser features a JSON response cannot
use).

CORS headers are not managed here. They are Starlette's ``CORSMiddleware``, which
has to answer preflights and negotiate per origin - reimplementing that would be
the opposite of hardening.
"""

from __future__ import annotations

from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, settings

#: Policy for API responses: a JSON document may do nothing at all.
API_CSP: Final[str] = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

#: Policy for the interactive documentation. Swagger UI and ReDoc are served as
#: HTML that loads its script and stylesheet from a CDN and applies inline styles,
#: so the strict policy above would render a blank page. This is scoped to exactly
#: the documentation paths, so relaxing it costs nothing on any route that carries
#: data. ``'unsafe-inline'`` is limited to styles; scripts still must come from the
#: named origins, so an injected inline script is still refused.
DOCS_CSP: Final[str] = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)

#: Paths served as HTML documents rather than as data.
DOCS_PATHS: Final[frozenset[str]] = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})


class SecurityHeadersMiddleware:
    """Add hardening headers to every response, including error responses."""

    def __init__(self, app: ASGIApp, config: Settings | None = None) -> None:
        self.app = app
        self.config = config or settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        csp = DOCS_CSP if scope.get("path") in DOCS_PATHS else API_CSP

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Frame-Options"] = "DENY"
                headers["Content-Security-Policy"] = csp
                headers["Cache-Control"] = "no-store"
                if self.config.hsts_active:
                    headers["Strict-Transport-Security"] = (
                        f"max-age={self.config.hsts_max_age_seconds}; "
                        "includeSubDomains"
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
