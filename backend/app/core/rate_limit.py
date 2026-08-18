"""Rate limiting primitives.

## What this is, and what it is not

This module implements a **fixed-window counter held in this process's memory**.
That is worth stating plainly because it decides what the limiter actually
protects against:

* It **does** stop a brute-force or request-storm from one client against one
  process. That is the common case: a script hammering ``/auth/login``, a mobile
  client stuck in a retry loop, someone flooding QR issuance.
* It **does not** give a shared limit across multiple API instances. With N
  instances behind a load balancer an attacker effectively gets N times the
  budget, because each process counts only what it saw. A genuinely distributed
  limit needs shared state - Redis - and Karya does not pretend otherwise. See
  ``docs/PRODUCTION.md``.
* It **does not** survive a restart. Counters are lost on deploy.

Neither limitation is papered over, and neither is a reason to skip the in-memory
version: it is real protection today, and the seam below means adding Redis later
touches this file and nothing else.

## The seam

Routes never talk to a limiter implementation. They depend on
:func:`app.api.limits.rate_limit`, which resolves :func:`get_rate_limiter`. A
Redis backend is a second class implementing :class:`RateLimiter` plus one line in
:func:`get_rate_limiter` - no route, schema or handler changes. The three methods
were chosen to map directly onto Redis primitives: :meth:`RateLimiter.consume` is
``INCR`` + ``EXPIRE``, :meth:`RateLimiter.peek` is ``GET``, and
:meth:`RateLimiter.clear` is ``DEL``.

## Why a fixed window

A fixed window admits up to ``2 * limit`` requests across a window boundary
(``limit`` at the end of one window, ``limit`` at the start of the next). A
sliding window or token bucket does not. The trade is deliberate: the fixed
window is the algorithm that ``INCR``/``EXPIRE`` implements natively and needs no
Lua script or per-key timestamp list, and for limits whose purpose is "make
guessing expensive" a factor of two at the boundary changes nothing material.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Protocol

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

#: How often the in-memory limiter sweeps expired windows, in seconds. Sweeping
#: on every call would be wasted work; never sweeping would leak one entry per
#: distinct key seen.
_SWEEP_INTERVAL_SECONDS: Final[float] = 60.0

MINUTE: Final[int] = 60
FIFTEEN_MINUTES: Final[int] = 15 * 60


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """A limit: ``limit`` events per ``window_seconds``."""

    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitVerdict:
    """The outcome of a limiter check."""

    allowed: bool
    #: Events still permitted in the current window (never negative).
    remaining: int
    #: Whole seconds until the current window resets. Sent as ``Retry-After``.
    retry_after_seconds: int

    @property
    def rejected(self) -> bool:
        return not self.allowed


class RateLimiter(Protocol):
    """The contract a rate-limit backend must satisfy."""

    def consume(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        """Count one event against ``key`` and report whether it is permitted."""
        ...

    def peek(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        """Report the state of ``key`` without counting an event."""
        ...

    def clear(self, key: str) -> None:
        """Forget ``key`` entirely."""
        ...

    def reset(self) -> None:
        """Forget every key. For tests and for a deliberate operator reset."""
        ...


@dataclass(slots=True)
class _Window:
    """One key's current counting window."""

    started_at: float
    count: int


class InMemoryRateLimiter:
    """Fixed-window limiter backed by a dict guarded by a lock.

    The lock is not optional. Karya's endpoints are ``def`` (not ``async def``),
    so Starlette runs them in a worker thread pool and several threads reach this
    dict at once; ``count += 1`` is not atomic across threads.

    Memory is bounded two ways: expired windows are swept periodically, and if the
    live key count still exceeds ``max_keys`` the limiter logs and evicts the
    windows closest to expiry. Eviction is a deliberate choice of "briefly forgive
    some callers" over "grow until the process is killed", and it is logged so the
    condition is visible rather than silent.
    """

    def __init__(self, *, max_keys: int, clock: object | None = None) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys
        # Injectable purely so tests can advance time instead of sleeping.
        self._clock = clock or time.monotonic
        self._last_sweep = self._now()

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    # --- RateLimiter ------------------------------------------------------
    def consume(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        now = self._now()
        with self._lock:
            self._maybe_sweep(now)
            window = self._live_window(key, rule, now)
            if window is None:
                self._windows[key] = _Window(started_at=now, count=1)
                self._enforce_capacity()
                return RateLimitVerdict(
                    allowed=True,
                    remaining=rule.limit - 1,
                    retry_after_seconds=rule.window_seconds,
                )
            if window.count >= rule.limit:
                return self._rejection(window, rule, now)
            window.count += 1
            return RateLimitVerdict(
                allowed=True,
                remaining=rule.limit - window.count,
                retry_after_seconds=self._retry_after(window, rule, now),
            )

    def peek(self, key: str, rule: RateLimitRule) -> RateLimitVerdict:
        now = self._now()
        with self._lock:
            window = self._live_window(key, rule, now)
            if window is None:
                return RateLimitVerdict(
                    allowed=True,
                    remaining=rule.limit,
                    retry_after_seconds=rule.window_seconds,
                )
            if window.count >= rule.limit:
                return self._rejection(window, rule, now)
            return RateLimitVerdict(
                allowed=True,
                remaining=rule.limit - window.count,
                retry_after_seconds=self._retry_after(window, rule, now),
            )

    def clear(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

    # --- internals --------------------------------------------------------
    def _live_window(
        self, key: str, rule: RateLimitRule, now: float
    ) -> _Window | None:
        """The key's window if it is still current, else ``None``.

        An expired window is dropped here rather than waiting for the sweep, so a
        caller who returns after the window lapsed starts from zero.
        """
        window = self._windows.get(key)
        if window is None:
            return None
        if now - window.started_at >= rule.window_seconds:
            del self._windows[key]
            return None
        return window

    @staticmethod
    def _retry_after(window: _Window, rule: RateLimitRule, now: float) -> int:
        elapsed = now - window.started_at
        remaining = rule.window_seconds - elapsed
        # Round up, and never report 0 - a client told to retry after 0 seconds
        # retries immediately and is rejected again.
        return max(1, int(remaining) + (1 if remaining % 1 else 0))

    def _rejection(
        self, window: _Window, rule: RateLimitRule, now: float
    ) -> RateLimitVerdict:
        return RateLimitVerdict(
            allowed=False,
            remaining=0,
            retry_after_seconds=self._retry_after(window, rule, now),
        )

    def _maybe_sweep(self, now: float) -> None:
        """Drop windows that can no longer reject anything.

        A window is only ever compared against the rule it was created with, and
        the longest rule Karya configures is 15 minutes, so anything older than
        that is dead regardless of which rule owns it.
        """
        if now - self._last_sweep < _SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        cutoff = now - FIFTEEN_MINUTES
        for key in [k for k, w in self._windows.items() if w.started_at < cutoff]:
            del self._windows[key]

    def _enforce_capacity(self) -> None:
        if len(self._windows) <= self._max_keys:
            return
        # Evict the oldest windows: they are closest to expiring anyway, so this
        # forgives the callers who have waited longest rather than the ones
        # currently generating the flood.
        overflow = len(self._windows) - self._max_keys
        oldest = sorted(self._windows.items(), key=lambda item: item[1].started_at)
        for key, _ in oldest[:overflow]:
            del self._windows[key]
        logger.warning(
            "rate_limiter_capacity_exceeded",
            extra={
                "event": "rate_limiter_capacity_exceeded",
                "max_keys": self._max_keys,
                "evicted": overflow,
            },
        )


class Rules:
    """The configured rule set, built from settings.

    Rules are read from configuration once per instance rather than per request,
    and the object is rebuilt if settings are replaced, so there is no per-request
    attribute lookup chain and no way for a route to invent its own limit inline.
    """

    def __init__(self, config: Settings) -> None:
        self.login = RateLimitRule(
            "login", config.rate_limit_login_per_minute, MINUTE
        )
        self.login_failures = RateLimitRule(
            "login_failures",
            config.rate_limit_login_failures_per_15_min,
            FIFTEEN_MINUTES,
        )
        self.refresh = RateLimitRule(
            "refresh", config.rate_limit_refresh_per_minute, MINUTE
        )
        self.password_change = RateLimitRule(
            "password_change",
            config.rate_limit_password_change_per_15_min,
            FIFTEEN_MINUTES,
        )
        self.qr_challenge = RateLimitRule(
            "qr_challenge", config.rate_limit_qr_challenge_per_minute, MINUTE
        )
        self.presence = RateLimitRule(
            "presence", config.rate_limit_presence_per_minute, MINUTE
        )
        self.attendance = RateLimitRule(
            "attendance", config.rate_limit_attendance_per_minute, MINUTE
        )
        self.admin_write = RateLimitRule(
            "admin_write", config.rate_limit_admin_write_per_minute, MINUTE
        )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Return the process-wide limiter.

    The single place a Redis-backed implementation would be substituted.
    """
    return InMemoryRateLimiter(max_keys=settings.rate_limit_max_tracked_keys)


@lru_cache(maxsize=1)
def get_rules() -> Rules:
    """Return the process-wide rule set."""
    return Rules(settings)


def identity_digest(*parts: str) -> str:
    """Stable, non-reversible key component for a personal identifier.

    Login failures are counted per (tenant, email), and an email is personal
    data. Hashing it keeps the counter working - the same input yields the same
    key - while ensuring a memory dump, a debug endpoint or a future Redis
    keyspace does not become a list of who has been trying to log in.
    """
    joined = "\x00".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]
