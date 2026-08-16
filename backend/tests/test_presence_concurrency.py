"""Concurrent QR consumption (spec check 29).

Unlike the rest of the suite these tests cannot run inside the shared
rolled-back transaction: genuine concurrency needs **separate committed
connections**, because two statements on one connection are serialised by
definition. So the fixture commits its rows and deletes them again in teardown.

This is also why the suite runs on PostgreSQL rather than SQLite. The property
under test is a PostgreSQL one: under READ COMMITTED (the default, and what the
application uses), a second UPDATE targeting an already-locked row blocks until
the first transaction commits, then re-evaluates its WHERE clause against the
newly committed row version. That re-evaluation is what turns the conditional
UPDATE into a compare-and-swap.

**The tests here force a deterministic interleaving** rather than starting
threads together and hoping they collide. Simply releasing N threads at once did
*not* reliably open the race window - the work per thread is a sub-millisecond
round trip, so the GIL often let one thread finish before the next began, and a
knowingly broken implementation passed. ``test_a_naive_read_then_write_would_
double_consume`` exists to keep that from silently happening again: it asserts
the harness can still catch the bug it is meant to catch.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceLocation,
    AuditLog,
    QRChallenge,
    QRChallengeStatus,
    RefreshToken,
    Tenant,
    User,
    UserRole,
)
from app.services.auth.password import hash_password
from app.services.presence import qr as qr_service
from app.services.presence import service as presence_service
from tests.conftest import (
    DEFAULT_PASSWORD,
    OFFICE_LATITUDE,
    OFFICE_LONGITUDE,
    offset_north,
)

#: Slug used only by this module, so teardown deletes exactly its own rows.
PROBE_SLUG = "concurrency-probe"

INSIDE_LATITUDE = offset_north(OFFICE_LATITUDE, 50.0)

#: How long to let the blocked transaction sit before concluding it is genuinely
#: waiting on a row lock rather than merely slow.
LOCK_WAIT_SECONDS = 1.0


@dataclass(frozen=True)
class Committed:
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    user_id: uuid.UUID
    challenge_id: uuid.UUID
    nonce: str

    def consume_kwargs(self) -> dict[str, object]:
        return {
            "challenge_id": self.challenge_id,
            "nonce": self.nonce,
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
        }


def _purge(engine: Engine, tenant_id: uuid.UUID) -> None:
    """Remove every row this module committed, in FK-safe order."""
    with Session(engine) as session:
        session.execute(delete(QRChallenge).where(QRChallenge.tenant_id == tenant_id))
        session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
        session.execute(delete(RefreshToken).where(RefreshToken.tenant_id == tenant_id))
        session.execute(
            delete(AttendanceLocation).where(AttendanceLocation.tenant_id == tenant_id)
        )
        session.execute(delete(User).where(User.tenant_id == tenant_id))
        session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        session.commit()


@pytest.fixture
def committed(engine: Engine) -> Iterator[Committed]:
    """A committed tenant + location + user + one ACTIVE challenge."""
    # Clear anything an interrupted earlier run left behind.
    with Session(engine) as session:
        stale = session.scalar(select(Tenant).where(Tenant.slug == PROBE_SLUG))
        stale_id = stale.id if stale is not None else None
    if stale_id is not None:
        _purge(engine, stale_id)

    with Session(engine) as session:
        tenant = Tenant(name="Concurrency Probe Ltd", slug=PROBE_SLUG)
        session.add(tenant)
        session.flush()

        location = AttendanceLocation(
            tenant_id=tenant.id,
            name="Head Office",
            latitude=OFFICE_LATITUDE,
            longitude=OFFICE_LONGITUDE,
            geofence_radius_meters=150,
        )
        user = User(
            tenant_id=tenant.id,
            employee_code="EMP-001",
            name="Rahul Sharma",
            email="rahul@concurrency-probe.com",
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.STAFF.value,
        )
        session.add_all([location, user])
        session.flush()

        challenge = QRChallenge(
            tenant_id=tenant.id,
            location_id=location.id,
            nonce=qr_service.generate_nonce(),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            status=QRChallengeStatus.ACTIVE.value,
        )
        session.add(challenge)
        session.commit()

        fixture = Committed(
            tenant_id=tenant.id,
            location_id=location.id,
            user_id=user.id,
            challenge_id=challenge.id,
            nonce=challenge.nonce,
        )

    try:
        yield fixture
    finally:
        _purge(engine, fixture.tenant_id)


@dataclass
class Interleaving:
    """Outcome of two transactions contending for the same challenge."""

    first: object
    second: object
    second_blocked: bool
    final_status: str | None


def interleave(
    engine: Engine,
    committed: Committed,
    operation: Callable[[Session, Committed], object],
) -> Interleaving:
    """Run ``operation`` in two transactions with a forced overlap.

    Transaction A performs the operation and *holds its transaction open*, so
    its row lock is still held. Transaction B then performs the same operation
    on another connection and must block on that lock. Once A commits, B
    proceeds and sees committed state.

    B runs on a thread because it blocks; A stays on the calling thread so the
    test controls exactly when the lock is released.
    """
    session_a = Session(engine)
    session_b = Session(engine)
    outcome: dict[str, object] = {}
    b_entered = threading.Event()

    try:
        first = operation(session_a, committed)
        session_a.flush()  # ensure the UPDATE has hit the database and locked

        def run_second() -> None:
            b_entered.set()
            outcome["value"] = operation(session_b, committed)
            session_b.commit()

        thread_b = threading.Thread(target=run_second, daemon=True)
        thread_b.start()
        assert b_entered.wait(timeout=10), "second transaction never started"
        time.sleep(LOCK_WAIT_SECONDS)

        # Still running => genuinely waiting on A's row lock, which is the
        # contention this test needs in order to mean anything.
        second_blocked = thread_b.is_alive()

        session_a.commit()
        thread_b.join(timeout=30)
        assert not thread_b.is_alive(), "second transaction deadlocked"
    finally:
        session_a.close()
        session_b.close()

    with Session(engine) as session:
        row = session.get(QRChallenge, committed.challenge_id)
        final_status = row.status if row is not None else None

    return Interleaving(
        first=first,
        second=outcome.get("value"),
        second_blocked=second_blocked,
        final_status=final_status,
    )


def _atomic_consume(session: Session, committed: Committed) -> bool:
    return qr_service.consume_challenge(session, **committed.consume_kwargs())  # type: ignore[arg-type]


def _naive_consume(session: Session, committed: Committed) -> bool:
    """The anti-pattern this design exists to avoid: read, decide, then write.

    Both transactions read ``status='ACTIVE'`` and both then write, because the
    write does not re-check what the read assumed.
    """
    challenge = session.scalar(
        select(QRChallenge)
        .where(QRChallenge.id == committed.challenge_id)
        .execution_options(populate_existing=True)
    )
    if challenge is None or challenge.status != QRChallengeStatus.ACTIVE:
        return False
    if challenge.used_at is not None or challenge.expires_at <= datetime.now(UTC):
        return False
    challenge.status = QRChallengeStatus.USED.value
    challenge.used_at = datetime.now(UTC)
    return True


# ---------------------------------------------------------------------------
# 29. Only one caller may ever consume a challenge
# ---------------------------------------------------------------------------


def test_second_consumer_blocks_then_fails(
    engine: Engine, committed: Committed
) -> None:
    """The core guarantee, under a forced overlap."""
    result = interleave(engine, committed, _atomic_consume)

    assert result.second_blocked, "no lock contention - the test proved nothing"
    assert result.first is True
    assert result.second is False
    assert result.final_status == QRChallengeStatus.USED


def test_a_naive_read_then_write_would_double_consume(
    engine: Engine, committed: Committed
) -> None:
    """Guards the test above from becoming vacuous.

    If this ever starts failing, the harness has stopped creating real
    contention and ``test_second_consumer_blocks_then_fails`` would pass no
    matter how the production code behaved.
    """
    result = interleave(engine, committed, _naive_consume)

    assert result.second_blocked
    assert result.first is True
    # Both "succeed" - exactly the replay hole the atomic UPDATE closes.
    assert result.second is True


def test_concurrent_presence_verification_verifies_only_one(
    engine: Engine, committed: Committed
) -> None:
    """The same guarantee through the full validate-then-consume flow.

    A naive implementation would let both callers pass the read-only QR check
    and then both report PRESENCE_VERIFIED.
    """

    def verify(session: Session, fixture: Committed) -> object:
        return presence_service.verify_presence(
            session,
            tenant_id=fixture.tenant_id,
            actor_user_id=fixture.user_id,
            latitude=INSIDE_LATITUDE,
            longitude=OFFICE_LONGITUDE,
            accuracy_meters=10.0,
            challenge_id=fixture.challenge_id,
            nonce=fixture.nonce,
        )

    result = interleave(engine, committed, verify)

    assert result.second_blocked
    assert result.first.verified is True  # type: ignore[union-attr]
    assert result.second.verified is False  # type: ignore[union-attr]
    assert result.final_status == QRChallengeStatus.USED


def test_loser_of_the_race_is_told_the_qr_was_already_used(
    engine: Engine, committed: Committed
) -> None:
    """The rejection must name the real cause, not assume one.

    The loser's UPDATE matched zero rows; it then re-reads the row to find out
    why. Under READ COMMITTED that re-read sees the winner's committed state.
    """

    def verify(session: Session, fixture: Committed) -> object:
        return presence_service.verify_presence(
            session,
            tenant_id=fixture.tenant_id,
            actor_user_id=fixture.user_id,
            latitude=INSIDE_LATITUDE,
            longitude=OFFICE_LONGITUDE,
            accuracy_meters=10.0,
            challenge_id=fixture.challenge_id,
            nonce=fixture.nonce,
        )

    result = interleave(engine, committed, verify)
    loser = result.second

    assert loser.verified is False  # type: ignore[union-attr]
    # GPS was valid for both callers; only the QR was contested.
    assert loser.gps.verified is True  # type: ignore[union-attr]
    assert loser.qr.verified is False  # type: ignore[union-attr]
    assert loser.reason is not None  # type: ignore[union-attr]
    assert loser.reason.value == "QR_ALREADY_USED"  # type: ignore[union-attr]


def test_repeated_attempts_yield_exactly_one_success(
    engine: Engine, committed: Committed
) -> None:
    """Eight independent transactions, one winner.

    These are started together but not guaranteed to overlap, so this is
    coverage of repeated independent attempts rather than of contention - the
    interleaving tests above carry that guarantee.
    """
    results: list[bool | None] = [None] * 8
    barrier = threading.Barrier(8, timeout=30)

    def attempt(index: int) -> None:
        with Session(engine) as session:
            barrier.wait()
            results[index] = qr_service.consume_challenge(
                session, **committed.consume_kwargs()  # type: ignore[arg-type]
            )
            session.commit()

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert sum(1 for value in results if value is True) == 1
    assert results.count(False) == 7

    with Session(engine) as session:
        row = session.get(QRChallenge, committed.challenge_id)
        assert row is not None
        assert row.status == QRChallengeStatus.USED
        assert row.used_at is not None
