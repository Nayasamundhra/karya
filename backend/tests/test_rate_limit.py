"""Rate limiting: the limiter, the endpoints, and what it must not break (Phase 7).

Three concerns, in order:

1. The limiter itself - windows, expiry, ``Retry-After``, capacity, thread safety.
   Tested with an injected clock, because a test that sleeps for 15 minutes to
   watch a window lapse is a test nobody runs.
2. The wiring - that the endpoints named in the specification are actually limited,
   with the configured budgets, and that a 429 says nothing extra.
3. The thing most worth protecting: **that a person using Karya normally never
   sees a 429.** A rate limiter that blocks a staff member from checking in is
   worse than no rate limiter, so a realistic day is exercised explicitly.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.core import rate_limit as rate_limit_module
from app.core.config import settings
from app.core.rate_limit import (
    FIFTEEN_MINUTES,
    MINUTE,
    InMemoryRateLimiter,
    RateLimitRule,
    Rules,
    get_rate_limiter,
    identity_digest,
)
from app.models import Tenant, User, UserRole
from tests.conftest import DEFAULT_PASSWORD, Org, auth_header

RULE = RateLimitRule("test", limit=3, window_seconds=60)


class FakeClock:
    """A monotonic clock a test can advance."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_keys=1_000, clock=clock)


# ---------------------------------------------------------------------------
# 1. The limiter
# ---------------------------------------------------------------------------


def test_the_first_requests_up_to_the_limit_are_allowed(
    limiter: InMemoryRateLimiter,
) -> None:
    remaining = [limiter.consume("k", RULE).remaining for _ in range(3)]

    assert remaining == [2, 1, 0]


def test_the_request_past_the_limit_is_rejected(limiter: InMemoryRateLimiter) -> None:
    for _ in range(3):
        assert limiter.consume("k", RULE).allowed

    verdict = limiter.consume("k", RULE)

    assert verdict.rejected
    assert verdict.remaining == 0


def test_a_rejection_does_not_extend_the_window(
    limiter: InMemoryRateLimiter, clock: FakeClock
) -> None:
    """Rejected attempts must not push the reset further out.

    Otherwise a client that keeps retrying is locked out forever - the behaviour a
    naive implementation produces and the one users notice.
    """
    for _ in range(3):
        limiter.consume("k", RULE)
    clock.advance(59)
    for _ in range(20):
        assert limiter.consume("k", RULE).rejected

    clock.advance(1)

    assert limiter.consume("k", RULE).allowed


def test_the_window_resets_once_it_lapses(
    limiter: InMemoryRateLimiter, clock: FakeClock
) -> None:
    for _ in range(3):
        limiter.consume("k", RULE)
    assert limiter.consume("k", RULE).rejected

    clock.advance(60)

    assert limiter.consume("k", RULE).allowed


def test_keys_are_independent(limiter: InMemoryRateLimiter) -> None:
    """One client's flood must not exhaust another client's budget."""
    for _ in range(3):
        limiter.consume("noisy", RULE)
    assert limiter.consume("noisy", RULE).rejected

    assert limiter.consume("quiet", RULE).allowed


def test_retry_after_counts_down_and_is_never_zero(
    limiter: InMemoryRateLimiter, clock: FakeClock
) -> None:
    """A client told to retry after 0 seconds retries at once and is rejected again."""
    for _ in range(3):
        limiter.consume("k", RULE)

    assert limiter.consume("k", RULE).retry_after_seconds == 60
    clock.advance(30)
    assert limiter.consume("k", RULE).retry_after_seconds == 30
    clock.advance(29.5)
    assert limiter.consume("k", RULE).retry_after_seconds == 1


def test_peek_reports_without_counting(limiter: InMemoryRateLimiter) -> None:
    """What login failure checking needs: ask, without spending budget."""
    for _ in range(10):
        assert limiter.peek("k", RULE).allowed
        assert limiter.peek("k", RULE).remaining == 3

    assert limiter.consume("k", RULE).allowed


def test_peek_reports_a_key_that_is_already_over_budget(
    limiter: InMemoryRateLimiter,
) -> None:
    for _ in range(3):
        limiter.consume("k", RULE)

    assert limiter.peek("k", RULE).rejected


def test_clear_forgets_one_key_only(limiter: InMemoryRateLimiter) -> None:
    """What a successful login does to its own failure counter."""
    for _ in range(3):
        limiter.consume("a", RULE)
        limiter.consume("b", RULE)

    limiter.clear("a")

    assert limiter.consume("a", RULE).allowed
    assert limiter.consume("b", RULE).rejected


def test_capacity_is_bounded(clock: FakeClock) -> None:
    """A flood of distinct addresses must not grow memory without limit."""
    small = InMemoryRateLimiter(max_keys=50, clock=clock)

    for index in range(500):
        small.consume(f"key-{index}", RULE)

    assert len(small._windows) <= 50


def test_expired_windows_are_swept(clock: FakeClock) -> None:
    swept = InMemoryRateLimiter(max_keys=1_000, clock=clock)
    for index in range(100):
        swept.consume(f"key-{index}", RULE)
    assert len(swept._windows) == 100

    # Past the longest configured window, then one more call to trigger the sweep.
    clock.advance(FIFTEEN_MINUTES + 1)
    swept.consume("trigger", RULE)

    assert len(swept._windows) == 1


def test_the_limiter_is_thread_safe() -> None:
    """Karya's endpoints are sync, so Starlette runs them in a thread pool and
    several threads reach the counter at once. ``count += 1`` is not atomic."""
    shared = InMemoryRateLimiter(max_keys=1_000)
    rule = RateLimitRule("burst", limit=500, window_seconds=60)
    allowed: list[bool] = []
    lock = threading.Lock()

    def hammer() -> None:
        results = [shared.consume("same-key", rule).allowed for _ in range(100)]
        with lock:
            allowed.extend(results)

    threads = [threading.Thread(target=hammer) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # 1000 attempts against a budget of 500: exactly 500 may pass. A lost update
    # would let more through.
    assert sum(allowed) == 500


def test_identifier_digests_are_stable_and_not_reversible() -> None:
    """Login failures are counted per email, and an email is personal data."""
    digest = identity_digest("acme", "rahul@acme.com")

    assert digest == identity_digest("acme", "rahul@acme.com")
    assert digest != identity_digest("acme", "priya@acme.com")
    # Same parts, different boundary: the separator prevents a collision between
    # ("ac", "me...") and ("acme", "...").
    assert identity_digest("ac", "merahul@acme.com") != digest
    assert "rahul@acme.com" not in digest
    assert "acme" not in digest


def test_rules_come_from_configuration() -> None:
    """No route may invent its own limit, and every limit must be tunable."""
    rules = Rules(settings)

    assert rules.login.limit == settings.rate_limit_login_per_minute
    assert rules.login.window_seconds == MINUTE
    assert rules.login_failures.window_seconds == FIFTEEN_MINUTES
    assert rules.attendance.limit == settings.rate_limit_attendance_per_minute
    assert rules.password_change.window_seconds == FIFTEEN_MINUTES


# ---------------------------------------------------------------------------
# 2. The endpoints
# ---------------------------------------------------------------------------


def test_login_is_limited_per_address(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    limit = settings.rate_limit_login_per_minute

    # Each attempt uses a *different* identifier, so only the per-address budget
    # can be what stops them.
    codes = [
        client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "acme",
                "email": f"user{index}@acme.com",
                "password": DEFAULT_PASSWORD,
            },
        ).status_code
        for index in range(limit + 2)
    ]

    assert codes[:limit] == [401] * limit
    assert codes[limit:] == [429, 429]


def test_a_429_carries_retry_after_and_says_nothing_else(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
) -> None:
    tenant_factory(slug="acme")
    for index in range(settings.rate_limit_login_per_minute + 1):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "acme",
                "email": f"user{index}@acme.com",
                "password": DEFAULT_PASSWORD,
            },
        )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    # Nothing about which limit was hit or how much budget remains: that would tell
    # a script exactly how to pace itself.
    assert response.json() == {"detail": "Too many requests"}


def test_repeated_wrong_passwords_for_one_account_are_throttled(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """The control that actually bounds guessing, since addresses are cheap."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    budget = settings.rate_limit_login_failures_per_15_min

    codes = [
        client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "acme",
                "email": "rahul@acme.com",
                "password": "wrong-password-guess",
            },
        ).status_code
        for _ in range(budget + 1)
    ]

    assert codes[:budget] == [401] * budget
    assert codes[budget] == 429


def test_throttling_an_unknown_account_looks_identical(
    client: TestClient, tenant_factory: Callable[..., Tenant]
) -> None:
    """The anti-enumeration guarantee has to hold for 429 as well as 401.

    If a real account throttled and a fictional one did not, the 429 itself would
    reveal which addresses exist.
    """
    tenant_factory(slug="acme")
    budget = settings.rate_limit_login_failures_per_15_min

    def attempt(email: str) -> Response:
        return client.post(
            "/api/v1/auth/login",
            json={"tenant_slug": "acme", "email": email, "password": "wrong-guess-1"},
        )

    for _ in range(budget):
        assert attempt("ghost@acme.com").status_code == 401
    throttled = attempt("ghost@acme.com")

    assert throttled.status_code == 429
    assert throttled.json() == {"detail": "Too many requests"}


def test_a_successful_login_clears_the_failure_counter(
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
) -> None:
    """Someone who mistypes their password and then gets it right must leave no
    trace - otherwise a clumsy morning locks them out."""
    tenant = tenant_factory(slug="acme")
    user_factory(tenant, email="rahul@acme.com")
    budget = settings.rate_limit_login_failures_per_15_min

    for _ in range(budget - 1):
        assert login("acme", "rahul@acme.com", "wrong-password").status_code == 401
    assert login("acme", "rahul@acme.com").status_code == 200

    # The budget is whole again, not one attempt from exhaustion.
    for _ in range(budget - 1):
        assert login("acme", "rahul@acme.com", "wrong-password").status_code == 401


def test_password_change_has_the_tightest_budget(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """It verifies a password, so an unlimited one is a guessing oracle."""
    org = org_factory()
    budget = settings.rate_limit_password_change_per_15_min

    codes = [
        client.post(
            "/api/v1/users/me/password",
            json={"current_password": "wrong-current", "new_password": "brand-new-1"},
            headers=auth_header(org.staff_token),
        ).status_code
        for _ in range(budget + 1)
    ]

    assert codes[:budget] == [401] * budget
    assert codes[budget] == 429


def test_qr_issuance_is_limited_per_issuer(
    client: TestClient,
    org_factory: Callable[..., Org],
    location_factory: Callable[..., object],
) -> None:
    org = org_factory()
    location_factory(org.tenant)
    budget = settings.rate_limit_qr_challenge_per_minute

    codes = [
        client.post(
            "/api/v1/presence/qr/challenge", headers=auth_header(org.manager_token)
        ).status_code
        for _ in range(budget + 1)
    ]

    assert codes[:budget] == [201] * budget
    assert codes[budget] == 429


def test_one_users_budget_is_not_another_users(
    client: TestClient,
    org_factory: Callable[..., Org],
    location_factory: Callable[..., object],
) -> None:
    """Per-user keying, not per-address: an office behind one public address must
    not share a single budget."""
    org = org_factory()
    location_factory(org.tenant)
    budget = settings.rate_limit_qr_challenge_per_minute

    for _ in range(budget + 1):
        client.post(
            "/api/v1/presence/qr/challenge", headers=auth_header(org.manager_token)
        )

    # The admin, from the same address, is unaffected.
    assert (
        client.post(
            "/api/v1/presence/qr/challenge", headers=auth_header(org.admin_token)
        ).status_code
        == 201
    )


def test_an_unauthenticated_caller_cannot_spend_a_users_budget(
    client: TestClient,
    org_factory: Callable[..., Org],
    location_factory: Callable[..., object],
) -> None:
    """Authentication runs before the counter, so a 401 costs nothing."""
    org = org_factory()
    location_factory(org.tenant)

    for _ in range(settings.rate_limit_qr_challenge_per_minute * 2):
        assert (
            client.post(
                "/api/v1/presence/qr/challenge",
                headers=auth_header("not-a-real-token"),
            ).status_code
            == 401
        )

    assert (
        client.post(
            "/api/v1/presence/qr/challenge", headers=auth_header(org.manager_token)
        ).status_code
        == 201
    )


def test_reads_are_not_rate_limited(
    client: TestClient, org_factory: Callable[..., Org]
) -> None:
    """Only mutations and credential checks carry a budget.

    Read endpoints are already bounded by pagination and range caps, and throttling
    a dashboard a manager refreshes would be user-visible for no security gain.
    """
    org = org_factory()

    for _ in range(settings.rate_limit_admin_write_per_minute + 5):
        assert (
            client.get(
                "/api/v1/attendance/team/today", headers=auth_header(org.admin_token)
            ).status_code
            == 200
        )


def test_limiting_can_be_switched_off(
    client: TestClient,
    tenant_factory: Callable[..., Tenant],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator running behind an edge limiter should be able to turn ours off.

    Checked at request time rather than at import, so the switch is real.
    """
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    tenant_factory(slug="acme")

    codes = [
        client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "acme",
                "email": "ghost@acme.com",
                "password": DEFAULT_PASSWORD,
            },
        ).status_code
        for _ in range(settings.rate_limit_login_per_minute + 5)
    ]

    assert set(codes) == {401}


# ---------------------------------------------------------------------------
# 3. Legitimate use must not be obstructed
# ---------------------------------------------------------------------------


def test_a_normal_working_day_never_hits_a_limit(
    db_session: Session,
    client: TestClient,
    login: Callable[..., Response],
    tenant_factory: Callable[..., Tenant],
    user_factory: Callable[..., User],
    location_factory: Callable[..., object],
) -> None:
    """The regression this suite most needs to catch.

    A staff member's real day: log in, check in, take a break, come back, check out.
    Every step needs its own fresh QR challenge, so this exercises the QR, presence
    and attendance budgets together against the same user.
    """
    tenant = tenant_factory(slug="acme")
    location = location_factory(tenant)
    manager = user_factory(
        tenant, email="priya@acme.com", employee_code="MGR-1", role=UserRole.MANAGER
    )
    user_factory(tenant, email="rahul@acme.com", employee_code="EMP-1")
    db_session.flush()

    manager_token = login("acme", "priya@acme.com").json()["access_token"]
    staff_token = login("acme", "rahul@acme.com").json()["access_token"]

    def qr() -> dict[str, str]:
        response = client.post(
            "/api/v1/presence/qr/challenge", headers=auth_header(manager_token)
        )
        assert response.status_code == 201, response.text
        body = response.json()
        return {"challenge_id": body["challenge_id"], "nonce": body["nonce"]}

    def act(path: str) -> Response:
        return client.post(
            path,
            json={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "accuracy_meters": 10.0,
                **qr(),
            },
            headers=auth_header(staff_token),
        )

    # In, out for lunch, back in, out for the day - four attendance actions, plus a
    # presence check before the first one, as a client might do to show a "you are
    # at the office" indicator.
    presence = client.post(
        "/api/v1/presence/verify",
        json={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "accuracy_meters": 10.0,
            **qr(),
        },
        headers=auth_header(staff_token),
    )
    assert presence.status_code == 200
    assert presence.json()["verified"] is True

    for index, path in enumerate((
        "/api/v1/attendance/check-in",
        "/api/v1/attendance/check-out",
        "/api/v1/attendance/check-in",
        "/api/v1/attendance/check-out",
    )):
        response = act(path)
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True, (index, path, response.text)

    # Plus the reads a client makes while the screen is open.
    for _ in range(10):
        assert (
            client.get(
                "/api/v1/attendance/me", headers=auth_header(staff_token)
            ).status_code
            == 200
        )


def test_the_process_wide_limiter_is_the_one_the_api_uses() -> None:
    """The seam a Redis backend would be substituted at.

    If ``get_rate_limiter`` ever returned a fresh instance per call, every limit
    would silently become no limit - the failure mode is invisible from the
    outside, so it is asserted here.
    """
    assert get_rate_limiter() is get_rate_limiter()
    assert isinstance(get_rate_limiter(), rate_limit_module.InMemoryRateLimiter)


def test_a_rejected_request_is_cheap(
    client: TestClient, tenant_factory: Callable[..., Tenant]
) -> None:
    """A 429 must be refused before the body is parsed.

    Otherwise the limiter still pays the cost of every request it rejects, which is
    most of what a flood costs.
    """
    tenant_factory(slug="acme")
    for index in range(settings.rate_limit_login_per_minute):
        client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": "acme",
                "email": f"u{index}@acme.com",
                "password": DEFAULT_PASSWORD,
            },
        )

    # A body that would be a 422 if it were validated at all.
    response = client.post(
        "/api/v1/auth/login", json={"nonsense": str(uuid.uuid4())}
    )

    assert response.status_code == 429
