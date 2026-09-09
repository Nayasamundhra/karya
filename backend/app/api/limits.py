"""Rate-limit dependencies for the API layer.

Routes declare *which* limit applies and nothing else:

    @router.post("/login", dependencies=[Depends(rate_limit_by_ip(lambda r: r.login))])

so the algorithm, the storage and the key scheme can all change without touching a
handler. See :mod:`app.core.rate_limit` for what the in-memory backend does and
does not protect against.

Two key scopes, chosen per endpoint by what the endpoint knows about its caller:

* **By client address** for unauthenticated endpoints (``/auth/login``,
  ``/auth/refresh``). There is no user yet, so the network peer is the only
  identity available.
* **By authenticated user id** for everything else. Far better than an address:
  it survives NAT - an entire office behind one public IP does not share a
  budget - and it cannot be rotated by an attacker with a pool of addresses.

The client address is taken from ``request.client.host`` and no proxy header is
parsed here. Behind a load balancer that address is the balancer's unless the
server is told to trust its forwarding header, which is uvicorn's job
(``--proxy-headers --forwarded-allow-ips=...``). Doing it in uvicorn rather than
here means one well-tested implementation and no second trust configuration to get
wrong - but it does mean a deployment that forgets the flag collapses every client
into one bucket. ``docs/PRODUCTION.md`` states this as a requirement.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import CurrentUser
from app.api.display_deps import CurrentDisplay, DisplayContext
from app.core.config import settings
from app.core.rate_limit import (
    RateLimitRule,
    RateLimitVerdict,
    Rules,
    get_rate_limiter,
    get_rules,
    identity_digest,
)
from app.models.user import User

logger = logging.getLogger(__name__)

#: Picks one rule out of the configured set. A callable rather than a string name
#: so a typo is a static error instead of a KeyError at request time.
RuleSelector = Callable[[Rules], RateLimitRule]

_TOO_MANY_REQUESTS = "Too many requests"

#: Shared OpenAPI fragment so every limited route documents 429 identically.
RATE_LIMITED_RESPONSE: dict[int | str, dict[str, str]] = {
    429: {"description": _TOO_MANY_REQUESTS}
}


def client_identity(request: Request) -> str:
    """The network peer's address, or a constant when it is unknown.

    A missing ``request.client`` happens with some ASGI transports. Falling back
    to a shared bucket is the safe direction: it may over-restrict, but it never
    hands out an unlimited budget.
    """
    return request.client.host if request.client else "unknown"


def _key(rule: RateLimitRule, scope: str, identity: str) -> str:
    return f"{rule.name}:{scope}:{identity}"


def _too_many_requests(verdict: RateLimitVerdict) -> HTTPException:
    """The one 429 raised anywhere.

    ``Retry-After`` is the contract a well-behaved client backs off on, so it is
    always populated. The body says nothing about which limit was hit or how much
    budget remains - that would tell a script exactly how to pace itself.
    """
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(verdict.retry_after_seconds)},
    )


def _enforce(rule: RateLimitRule, scope: str, identity: str) -> None:
    """Count one event and raise 429 if the limit is now exceeded."""
    if not settings.rate_limit_enabled:
        return
    verdict = get_rate_limiter().consume(_key(rule, scope, identity), rule)
    if verdict.rejected:
        logger.warning(
            "rate_limited",
            extra={
                "event": "rate_limited",
                "rule": rule.name,
                "scope": scope,
                "retry_after_seconds": verdict.retry_after_seconds,
            },
        )
        raise _too_many_requests(verdict)


def rate_limit_by_ip(select: RuleSelector) -> Callable[[Request], None]:
    """Dependency limiting an endpoint per client address."""

    def dependency(request: Request) -> None:
        _enforce(select(get_rules()), "ip", client_identity(request))

    return dependency


def rate_limit_by_user(select: RuleSelector) -> Callable[[User], None]:
    """Dependency limiting an endpoint per authenticated user.

    Depends on the authentication dependency, so an unauthenticated request is
    rejected with 401 before any counter moves - a caller with no credentials
    cannot consume a legitimate user's budget.
    """

    def dependency(current_user: CurrentUser) -> None:
        _enforce(select(get_rules()), "user", str(current_user.id))

    return dependency


def rate_limit_by_display(select: RuleSelector) -> Callable[[DisplayContext], None]:
    """Dependency limiting an endpoint per display-token identity.

    Mirrors `rate_limit_by_user`, keyed on the kiosk's own token id rather
    than a user id - a display token is not a user (see
    `app.api.display_deps`), so it gets its own key namespace rather than
    sharing one with `rate_limit_by_user`.
    """

    def dependency(display: CurrentDisplay) -> None:
        _enforce(select(get_rules()), "display", str(display.display_token_id))

    return dependency


# ---------------------------------------------------------------------------
# Login failure counting
# ---------------------------------------------------------------------------
#
# The per-address limit above bounds request volume. It does not bound *guessing*:
# an attacker with many addresses still gets many attempts at one account. So
# failed logins are counted per (tenant, email) as well.
#
# Only failures count, and a success clears the counter. That is what keeps the
# control invisible to a real person: someone who mistypes their password twice
# and then gets it right leaves no trace, while a script that never succeeds runs
# out of budget.
#
# The counter is keyed on a digest of the identifier, never the address itself -
# see `identity_digest`.
#
# Trade-off, stated rather than hidden: an attacker who knows an email can spend
# the budget deliberately and lock that account out of *this process* for up to
# the window. That is inherent to per-account throttling. It is mitigated by
# counting only failures, by a window measured in minutes rather than hours, and
# by a limit high enough that ordinary mistyping never reaches it - but it is a
# real trade, not an absence of one.


def _login_failure_key(tenant_slug: str, email: str) -> str:
    rule = get_rules().login_failures
    return _key(rule, "identity", identity_digest(tenant_slug.lower(), email.lower()))


def guard_login_failures(tenant_slug: str, email: str) -> None:
    """Refuse a login attempt for an identifier that has failed too often.

    Checked *without* counting: the attempt itself is counted by the per-address
    limit, and counting here too would mean a valid password consumed failure
    budget.

    The same 429 is returned whether or not the account exists, so this cannot be
    used to discover which identifiers are real - the Phase 2 anti-enumeration
    property has to hold for every status code, not just 401.

    Raises:
        HTTPException: 429 when the identifier is over its failure budget.
    """
    if not settings.rate_limit_enabled:
        return
    rule = get_rules().login_failures
    verdict = get_rate_limiter().peek(_login_failure_key(tenant_slug, email), rule)
    if verdict.rejected:
        logger.warning(
            "login_throttled",
            extra={
                "event": "login_throttled",
                "rule": rule.name,
                "retry_after_seconds": verdict.retry_after_seconds,
            },
        )
        raise _too_many_requests(verdict)


def record_login_failure(tenant_slug: str, email: str) -> None:
    """Count one failed login against an identifier."""
    if not settings.rate_limit_enabled:
        return
    get_rate_limiter().consume(
        _login_failure_key(tenant_slug, email), get_rules().login_failures
    )


def clear_login_failures(tenant_slug: str, email: str) -> None:
    """Forget an identifier's failures after a successful login."""
    if not settings.rate_limit_enabled:
        return
    get_rate_limiter().clear(_login_failure_key(tenant_slug, email))


# ---------------------------------------------------------------------------
# Ready-made dependencies
# ---------------------------------------------------------------------------
# Declared once here rather than as inline lambdas at each route, so the whole set
# of rate-limited endpoints is enumerable by reading one place. Routes attach them
# through `dependencies=[...]` because they are pure side effects - a handler has
# no use for the return value.
#
# These run before the request body is parsed, so a throttled caller is refused
# without Karya spending anything on decoding what they sent.

LOGIN_RATE_LIMIT = Depends(rate_limit_by_ip(lambda rules: rules.login))
REFRESH_RATE_LIMIT = Depends(rate_limit_by_ip(lambda rules: rules.refresh))
PASSWORD_CHANGE_RATE_LIMIT = Depends(
    rate_limit_by_user(lambda rules: rules.password_change)
)
QR_CHALLENGE_RATE_LIMIT = Depends(rate_limit_by_user(lambda rules: rules.qr_challenge))
PRESENCE_RATE_LIMIT = Depends(rate_limit_by_user(lambda rules: rules.presence))
ATTENDANCE_RATE_LIMIT = Depends(rate_limit_by_user(lambda rules: rules.attendance))
ADMIN_WRITE_RATE_LIMIT = Depends(rate_limit_by_user(lambda rules: rules.admin_write))
#: Public, per-IP - the one unauthenticated write endpoint in the API.
ONBOARDING_RATE_LIMIT = Depends(rate_limit_by_ip(lambda rules: rules.onboarding))
#: Public, per-IP, separate budget from onboarding itself (see Settings docstring).
EMAIL_VERIFICATION_RATE_LIMIT = Depends(
    rate_limit_by_ip(lambda rules: rules.email_verification)
)
#: Per display-token identity, not per user - matches "the office display
#: refreshes roughly twice a minute" reasoning already used for QR_CHALLENGE_RATE_LIMIT.
DISPLAY_QR_CHALLENGE_RATE_LIMIT = Depends(
    rate_limit_by_display(lambda rules: rules.qr_challenge)
)
#: A kiosk resetting itself is rare (a device being repurposed or a lost
#: token), so it shares the low-volume admin_write budget rather than
#: warranting its own config setting.
DISPLAY_SELF_REVOKE_RATE_LIMIT = Depends(
    rate_limit_by_display(lambda rules: rules.admin_write)
)
