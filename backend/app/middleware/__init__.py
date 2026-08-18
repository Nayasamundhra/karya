"""ASGI middleware.

Every middleware here is written against the raw ASGI interface rather than
Starlette's ``BaseHTTPMiddleware``. That is deliberate: ``BaseHTTPMiddleware``
runs the downstream application in a separate task connected by a queue, which
costs an extra task switch per request and interferes with streaming responses and
background tasks. These middlewares only need to read the scope and wrap ``send``,
which the plain interface does with no such cost.

They are mounted in :mod:`app.main`, outermost first:

1. :class:`~app.middleware.request_context.RequestContextMiddleware` - correlation
   id, access log, last-resort 500. Outermost so it observes every request,
   including ones rejected by the middleware below it.
2. :class:`~app.middleware.security_headers.SecurityHeadersMiddleware` - response
   hardening headers, applied to every response including error responses.
3. :class:`~app.middleware.request_limits.RequestLimitsMiddleware` - size limits,
   applied before the body is read or parsed.
"""
