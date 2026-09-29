"""Concurrent check-in / check-out, and concurrent auto-close of a stale session.

Separate committed connections and a **forced interleaving**, because
releasing N threads together does not reliably open the race window - each
request is a sub-millisecond round trip, so a knowingly broken implementation
passes.

Transaction A performs the action and holds its transaction open; B then does
the same on another connection and must block on A's ``SELECT ... FOR UPDATE``
of the user row. ``test_a_naive_unlocked_check_in_would_double_insert`` and
``test_a_naive_unlocked_auto_close_would_double_insert`` keep this honest by
asserting an implementation without that lock *does* produce two events under
the identical interleaving.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AttendanceEventType,
    AttendanceLocation,
    AuditLog,
    RefreshToken,
    Tenant,
    User,
    UserRole,
    VerificationStatus,
)
from app.models.attendance_location import DEFAULT_MAX_SHIFT_HOURS
from app.services.attendance import service as attendance_service
from app.services.attendance.results import (
    STATE_AFTER_EVENT,
    STATE_REQUIRED_FOR_EVENT,
    AttendanceOutcome,
    AttendanceState,
)
from app.services.auth.password import hash_password
from app.services.presence import service as presence_service
from tests.conftest import (
    DEFAULT_PASSWORD,
    OFFICE_LATITUDE,
    OFFICE_LONGITUDE,
    offset_north,
)

PROBE_SLUG = "attendance-race-probe"
INSIDE = offset_north(OFFICE_LATITUDE, 50.0)
LOCK_WAIT_SECONDS = 1.0


@dataclass(frozen=True)
class Fixture:
    tenant_id: uuid.UUID
    location_id: uuid.UUID
    user_id: uuid.UUID
    qr_token: uuid.UUID

    def evidence(self, index: int = 0) -> dict:
        """``index`` is vestigial - kept so call sites reading like "the second
        attempt" still make sense - but the static QR is the same value on
        every call, unlike the old per-challenge one it replaced.
        """
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "latitude": INSIDE,
            "longitude": OFFICE_LONGITUDE,
            "accuracy_meters": 10.0,
            "qr_token": self.qr_token,
        }


def _purge(engine: Engine, tenant_id: uuid.UUID) -> None:
    with Session(engine) as session:
        for model in (AuditLog, RefreshToken, AttendanceEvent):
            session.execute(delete(model).where(model.tenant_id == tenant_id))
        session.execute(
            delete(AttendanceLocation).where(AttendanceLocation.tenant_id == tenant_id)
        )
        session.execute(delete(User).where(User.tenant_id == tenant_id))
        session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        session.commit()


@pytest.fixture
def committed(engine: Engine) -> Iterator[Fixture]:
    """A committed tenant, site and user."""
    with Session(engine) as session:
        stale = session.scalar(select(Tenant).where(Tenant.slug == PROBE_SLUG))
        stale_id = stale.id if stale is not None else None
    if stale_id is not None:
        _purge(engine, stale_id)

    with Session(engine) as session:
        tenant = Tenant(name="Attendance Race Probe", slug=PROBE_SLUG)
        session.add(tenant)
        session.flush()
        location = AttendanceLocation(
            tenant_id=tenant.id,
            name="HQ",
            latitude=OFFICE_LATITUDE,
            longitude=OFFICE_LONGITUDE,
            geofence_radius_meters=150,
        )
        user = User(
            tenant_id=tenant.id,
            employee_code="EMP-1",
            name="Rahul",
            email="rahul@attendance-race-probe.com",
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.STAFF.value,
        )
        session.add_all([location, user])
        session.commit()

        fixture = Fixture(
            tenant_id=tenant.id,
            location_id=location.id,
            user_id=user.id,
            qr_token=location.qr_token,
        )

    try:
        yield fixture
    finally:
        _purge(engine, fixture.tenant_id)


@dataclass
class Interleaving:
    first: AttendanceOutcome
    second: AttendanceOutcome
    second_blocked: bool


def interleave(
    engine: Engine,
    operation: Callable[[Session, int], AttendanceOutcome],
) -> Interleaving:
    """Run ``operation`` twice with a forced overlap; B must block on A's lock."""
    session_a = Session(engine)
    session_b = Session(engine)
    outcome: dict[str, AttendanceOutcome] = {}
    b_entered = threading.Event()

    try:
        first = operation(session_a, 0)
        session_a.flush()

        def run_second() -> None:
            b_entered.set()
            outcome["value"] = operation(session_b, 1)
            session_b.commit()

        thread_b = threading.Thread(target=run_second, daemon=True)
        thread_b.start()
        assert b_entered.wait(timeout=10), "second transaction never started"
        time.sleep(LOCK_WAIT_SECONDS)

        second_blocked = thread_b.is_alive()

        session_a.commit()
        thread_b.join(timeout=30)
        assert not thread_b.is_alive(), "second transaction deadlocked"
    finally:
        session_a.close()
        session_b.close()

    return Interleaving(
        first=first, second=outcome["value"], second_blocked=second_blocked
    )


def count_events(engine: Engine, tenant_id: uuid.UUID, event_type: str) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(AttendanceEvent)
            .where(
                AttendanceEvent.tenant_id == tenant_id,
                AttendanceEvent.event_type == event_type,
            )
        ) or 0


def _naive_record(
    session: Session, fixture: Fixture, index: int, event_type: AttendanceEventType
) -> AttendanceOutcome:
    """The same flow **without** the user row lock.

    Both transactions read the state before either writes, so both believe the
    transition is legal. This is the bug the lock exists to prevent.
    """
    kwargs = fixture.evidence(index)
    state = attendance_service.get_current_state(
        session, tenant_id=kwargs["tenant_id"], user_id=kwargs["user_id"]
    )
    if state is not STATE_REQUIRED_FOR_EVENT[event_type]:
        return AttendanceOutcome(
            success=False, event_type=event_type, state=state, reason=None
        )

    decision = presence_service.verify_presence(
        session,
        tenant_id=kwargs["tenant_id"],
        actor_user_id=kwargs["user_id"],
        latitude=kwargs["latitude"],
        longitude=kwargs["longitude"],
        accuracy_meters=kwargs["accuracy_meters"],
        qr_token=kwargs["qr_token"],
        audit_failures=False,
    )
    if not decision.verified:
        return AttendanceOutcome(
            success=False, event_type=event_type, state=state, reason=None
        )

    event = AttendanceEvent(
        tenant_id=kwargs["tenant_id"],
        user_id=kwargs["user_id"],
        event_type=event_type.value,
        verification_status="VERIFIED",
        verification_metadata={},
    )
    session.add(event)
    session.flush()
    return AttendanceOutcome(
        success=True,
        event_type=event_type,
        state=STATE_AFTER_EVENT[event_type],
        event_id=event.id,
    )


# ---------------------------------------------------------------------------
# 37. Concurrent check-in
# ---------------------------------------------------------------------------


def test_two_simultaneous_check_ins_produce_exactly_one(
    engine: Engine, committed: Fixture
) -> None:
    def action(session: Session, index: int) -> AttendanceOutcome:
        return attendance_service.check_in(session, **committed.evidence(index))

    result = interleave(engine, action)

    assert result.second_blocked, "no lock contention - the test proved nothing"
    assert result.first.success is True
    assert result.second.success is False
    assert result.second.reason is not None
    assert result.second.reason.value == "ALREADY_CHECKED_IN"
    assert count_events(engine, committed.tenant_id, "CHECK_IN") == 1


def test_a_naive_unlocked_check_in_would_double_insert(
    engine: Engine, committed: Fixture
) -> None:
    """Guards the test above from becoming vacuous.

    If this stops failing, the harness has stopped creating real contention and
    the locked test would pass regardless of the production code.
    """

    def action(session: Session, index: int) -> AttendanceOutcome:
        return _naive_record(
            session, committed, index, AttendanceEventType.CHECK_IN
        )

    result = interleave(engine, action)

    assert result.first.success is True
    # Both "succeed" - two CHECK_INs in a row, the broken state machine.
    assert result.second.success is True
    assert count_events(engine, committed.tenant_id, "CHECK_IN") == 2


# ---------------------------------------------------------------------------
# 38. Concurrent check-out
# ---------------------------------------------------------------------------


def test_two_simultaneous_check_outs_produce_exactly_one(
    engine: Engine, committed: Fixture
) -> None:
    # Establish CHECKED_IN first, in its own committed transaction.
    with Session(engine) as session:
        outcome = attendance_service.check_in(session, **committed.evidence(0))
        assert outcome.success is True
        session.commit()

    def action(session: Session, index: int) -> AttendanceOutcome:
        return attendance_service.check_out(session, **committed.evidence())

    result = interleave(engine, action)

    assert result.second_blocked
    assert result.first.success is True
    assert result.second.success is False
    assert result.second.reason is not None
    assert result.second.reason.value == "NOT_CHECKED_IN"
    assert count_events(engine, committed.tenant_id, "CHECK_OUT") == 1


# ---------------------------------------------------------------------------
# 39. The database is left in a valid state
# ---------------------------------------------------------------------------


def test_concurrent_operations_leave_a_strictly_alternating_sequence(
    engine: Engine, committed: Fixture
) -> None:
    """After contested check-in and check-out, the event log must still alternate."""

    def check_in_action(session: Session, index: int) -> AttendanceOutcome:
        return attendance_service.check_in(session, **committed.evidence(index))

    interleave(engine, check_in_action)

    def check_out_action(session: Session, index: int) -> AttendanceOutcome:
        return attendance_service.check_out(session, **committed.evidence(index + 2))

    interleave(engine, check_out_action)

    with Session(engine) as session:
        events = session.scalars(
            select(AttendanceEvent)
            .where(AttendanceEvent.tenant_id == committed.tenant_id)
            .order_by(AttendanceEvent.event_timestamp, AttendanceEvent.created_at)
        ).all()

    assert [e.event_type for e in events] == ["CHECK_IN", "CHECK_OUT"]
    assert all(a.event_type != b.event_type for a, b in zip(events, events[1:]))
    assert (
        attendance_service.get_current_state(
            Session(engine), tenant_id=committed.tenant_id, user_id=committed.user_id
        )
        is AttendanceState.NOT_CHECKED_IN
    )


# ---------------------------------------------------------------------------
# Event ordering under contention (Phase 7)
# ---------------------------------------------------------------------------
#
# The row lock serialises the *decision*. It cannot serialise a timestamp that was
# already fixed when the transaction began - which is exactly what
# `DEFAULT now()` is, since `now()` returns the transaction start time.
#
# So the interleaving below is the reverse of the one above: B's transaction begins
# FIRST and then blocks on A's lock. Under `now()` that produced a legitimate
# CHECK_OUT stamped *earlier* than the CHECK_IN it followed, and the derived state
# stayed CHECKED_IN for a user who had checked out.


@dataclass
class ReverseInterleaving:
    """Outcomes of an interleaving where B's transaction began before A's."""

    first: AttendanceOutcome
    second: AttendanceOutcome
    second_blocked: bool


def interleave_with_older_second_transaction(
    engine: Engine,
    operation: Callable[[Session, int], AttendanceOutcome],
) -> ReverseInterleaving:
    """Run ``operation`` twice, with B's transaction *older* than A's.

    B is forced to BEGIN first (a trivial statement starts its transaction and
    therefore fixes its ``now()``), then A begins, takes the user row lock and acts.
    B only reaches the lock afterwards, so B commits second while carrying the
    earlier transaction timestamp - the ordering hazard being tested.
    """
    session_a = Session(engine)
    session_b = Session(engine)
    outcome: dict[str, AttendanceOutcome] = {}
    b_entered = threading.Event()

    try:
        # B's transaction starts here, before A exists at all.
        session_b.execute(select(func.now()))
        time.sleep(0.2)

        first = operation(session_a, 0)
        session_a.flush()

        def run_second() -> None:
            b_entered.set()
            outcome["value"] = operation(session_b, 1)
            session_b.commit()

        thread_b = threading.Thread(target=run_second, daemon=True)
        thread_b.start()
        assert b_entered.wait(timeout=10), "second transaction never started"
        time.sleep(LOCK_WAIT_SECONDS)

        second_blocked = thread_b.is_alive()

        session_a.commit()
        thread_b.join(timeout=30)
        assert not thread_b.is_alive(), "second transaction deadlocked"
    finally:
        session_a.close()
        session_b.close()

    return ReverseInterleaving(
        first=first, second=outcome["value"], second_blocked=second_blocked
    )


def stored_event_types(engine: Engine, tenant_id: uuid.UUID) -> list[str]:
    with Session(engine) as session:
        return [
            event.event_type
            for event in session.scalars(
                select(AttendanceEvent)
                .where(AttendanceEvent.tenant_id == tenant_id)
                .order_by(AttendanceEvent.event_timestamp)
            )
        ]


def test_a_check_out_committed_second_is_never_stamped_before_the_check_in(
    engine: Engine, committed: Fixture
) -> None:
    """The regression this migration exists for.

    A checks in; B - whose transaction is older - was blocked on the lock, wakes,
    correctly sees CHECKED_IN and checks out. Both succeed, and the stored order
    must match the order they actually happened in.
    """

    def action(session: Session, index: int) -> AttendanceOutcome:
        if index == 0:
            return attendance_service.check_in(session, **committed.evidence(0))
        return attendance_service.check_out(session, **committed.evidence(1))

    result = interleave_with_older_second_transaction(engine, action)

    assert result.second_blocked, "no lock contention - the test proved nothing"
    assert result.first.success is True
    assert result.second.success is True

    assert stored_event_types(engine, committed.tenant_id) == ["CHECK_IN", "CHECK_OUT"]
    with Session(engine) as session:
        assert (
            attendance_service.get_current_state(
                session, tenant_id=committed.tenant_id, user_id=committed.user_id
            )
            is AttendanceState.NOT_CHECKED_IN
        )


def test_a_now_default_would_invert_the_pair(
    engine: Engine, committed: Fixture
) -> None:
    """Guards the test above from becoming vacuous.

    Stamps each event with ``now()`` explicitly - reproducing exactly what the
    pre-Phase-7 column default did - under the identical interleaving. If this stops
    failing, the harness has stopped producing an older second transaction and the
    test above would pass regardless of the column default.
    """

    def action(session: Session, index: int) -> AttendanceOutcome:
        event_type = (
            AttendanceEventType.CHECK_IN if index == 0 else AttendanceEventType.CHECK_OUT
        )
        outcome = (
            attendance_service.check_in(session, **committed.evidence(0))
            if index == 0
            else attendance_service.check_out(session, **committed.evidence(1))
        )
        # Overwrite with the transaction-start time, which is what `now()` yields.
        session.execute(
            AttendanceEvent.__table__.update()
            .where(AttendanceEvent.id == outcome.event_id)
            .values(event_timestamp=func.now())
        )
        assert outcome.event_type is event_type
        return outcome

    result = interleave_with_older_second_transaction(engine, action)

    assert result.first.success is True
    assert result.second.success is True
    # Inverted: the CHECK_OUT carries the older transaction's timestamp.
    assert stored_event_types(engine, committed.tenant_id) == ["CHECK_OUT", "CHECK_IN"]
    with Session(engine) as session:
        # And the user is left looking checked in, which is the actual harm.
        assert (
            attendance_service.get_current_state(
                session, tenant_id=committed.tenant_id, user_id=committed.user_id
            )
            is AttendanceState.CHECKED_IN
        )


def test_events_written_in_one_transaction_get_distinct_timestamps(
    engine: Engine, committed: Fixture
) -> None:
    """``now()`` is constant within a transaction, so two events written in one
    shared a timestamp and the "latest event" query broke the tie arbitrarily -
    differently depending on whether the planner chose a sequential or index scan.
    """
    with Session(engine) as session:
        first = attendance_service.check_in(session, **committed.evidence(0))
        second = attendance_service.check_out(session, **committed.evidence(1))
        session.commit()

        assert first.success and second.success
        stamps = [
            event.event_timestamp
            for event in session.scalars(
                select(AttendanceEvent)
                .where(AttendanceEvent.tenant_id == committed.tenant_id)
                .order_by(AttendanceEvent.event_timestamp)
            )
        ]

    assert len(set(stamps)) == 2, "two events in one transaction shared a timestamp"
    assert stored_event_types(engine, committed.tenant_id) == ["CHECK_IN", "CHECK_OUT"]


# ---------------------------------------------------------------------------
# Concurrent auto-close of a forgotten checkout
# ---------------------------------------------------------------------------
#
# `close_stale_session_for_user` and the in-band check inside `record_attendance`
# can both discover the same stale CHECK_IN at once - one from the standalone
# sweep (`app/jobs/close_stale_sessions.py`), one from the user's own next
# check-in landing at the same instant. Both take the same user-row lock before
# deciding anything, so only one of them ever writes the AUTO_CLOSED event; the
# second finds it already closed and does nothing.


def _make_stale_check_in(engine: Engine, fixture: Fixture) -> None:
    """Commit a CHECK_IN older than the configured cutoff, directly."""
    with Session(engine) as session:
        stale_at = datetime.now(UTC) - timedelta(
            hours=DEFAULT_MAX_SHIFT_HOURS, minutes=5
        )
        session.add(
            AttendanceEvent(
                tenant_id=fixture.tenant_id,
                user_id=fixture.user_id,
                event_type=AttendanceEventType.CHECK_IN.value,
                event_timestamp=stale_at,
                verification_status="VERIFIED",
                verification_metadata={},
            )
        )
        session.commit()


def _naive_close(session: Session, fixture: Fixture, _index: int) -> bool:
    """The same auto-close, **without** the user row lock: read, then write.

    Both transactions read the stale CHECK_IN before either has written its
    closing event, so both believe one is needed - the bug the lock exists to
    prevent.
    """
    latest = attendance_service.get_latest_event(
        session, tenant_id=fixture.tenant_id, user_id=fixture.user_id
    )
    if latest is None or AttendanceEventType(latest.event_type) is not (
        AttendanceEventType.CHECK_IN
    ):
        return False
    cutoff = timedelta(hours=DEFAULT_MAX_SHIFT_HOURS)
    if datetime.now(UTC) - latest.event_timestamp <= cutoff:
        return False

    session.add(
        AttendanceEvent(
            tenant_id=fixture.tenant_id,
            user_id=fixture.user_id,
            event_type=AttendanceEventType.CHECK_OUT.value,
            verification_status=VerificationStatus.AUTO_CLOSED.value,
            verification_metadata={},
        )
    )
    session.flush()
    return True


def count_auto_closed(engine: Engine, tenant_id: uuid.UUID) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(AttendanceEvent)
            .where(
                AttendanceEvent.tenant_id == tenant_id,
                AttendanceEvent.verification_status == VerificationStatus.AUTO_CLOSED.value,
            )
        ) or 0


def test_two_concurrent_auto_closes_produce_exactly_one_event(
    engine: Engine, committed: Fixture
) -> None:
    _make_stale_check_in(engine, committed)

    def action(session: Session, _index: int) -> bool:
        return attendance_service.close_stale_session_for_user(
            session, tenant_id=committed.tenant_id, user_id=committed.user_id
        )

    result = interleave(engine, action)

    assert result.second_blocked, "no lock contention - the test proved nothing"
    assert result.first is True
    # The second call finds the session already closed - a no-op, not a failure.
    assert result.second is False
    assert count_auto_closed(engine, committed.tenant_id) == 1


def test_a_naive_unlocked_auto_close_would_double_insert(
    engine: Engine, committed: Fixture
) -> None:
    """Guards the test above from becoming vacuous.

    If this stops failing, the harness has stopped creating real contention
    and the locked test would pass regardless of the production code.
    """
    _make_stale_check_in(engine, committed)

    def action(session: Session, index: int) -> bool:
        return _naive_close(session, committed, index)

    result = interleave(engine, action)

    assert result.first is True
    # Both "succeed" - two AUTO_CLOSED events for one stale CHECK_IN.
    assert result.second is True
    assert count_auto_closed(engine, committed.tenant_id) == 2


def test_a_returning_check_in_closes_a_stale_session_and_proceeds(
    engine: Engine, committed: Fixture
) -> None:
    """The common case: no sweep needed, the next check-in closes it inline."""
    _make_stale_check_in(engine, committed)

    with Session(engine) as session:
        outcome = attendance_service.check_in(session, **committed.evidence())
        session.commit()

    assert outcome.success is True
    assert outcome.auto_closed_previous_session is True
    assert count_auto_closed(engine, committed.tenant_id) == 1
    assert (
        attendance_service.get_current_state(
            Session(engine), tenant_id=committed.tenant_id, user_id=committed.user_id
        )
        is AttendanceState.CHECKED_IN
    )
