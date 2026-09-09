"""The display-token heartbeat lookup, raced against a concurrent revoke.

`get_current_display` (`app.api.display_deps`) claims in its own docstring
that "a revoked-in-another-request race can't leave a stale heartbeat" -
this is the forced-interleaving proof for that claim, in the same style as
the other `*_concurrency.py` modules: two real connections, a deliberately
held transaction to force genuine overlap, and an assertion that the loser
sees the winner's committed state rather than stale data.

Both `revoke_display_token` and `get_current_display` write via a plain
`UPDATE` (no `SELECT ... FOR UPDATE`), so the guarantee here rests on
PostgreSQL's own read-committed behaviour: the second UPDATE to reach a row
blocks on the first's row lock, then re-evaluates its own `WHERE` clause
against the just-committed data once unblocked. This test is what would
catch that guarantee ever regressing (e.g. an unrelated change that reads
`revoked_at` before taking the row lock instead of as part of the `UPDATE`).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.api.display_deps import get_current_display
from app.models import AttendanceLocation, Tenant, User, UserRole
from app.models.audit_log import AuditLog
from app.models.display_token import DisplayToken
from app.services.presence import display as display_service

PROBE_SLUG = "display-race-probe"
LOCK_WAIT_SECONDS = 1.0


@dataclass(frozen=True)
class Fixture:
    tenant_id: uuid.UUID
    display_token_id: uuid.UUID
    raw_token: str
    admin_id: uuid.UUID


def _purge(engine: Engine, slug: str) -> None:
    with Session(engine) as session:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            return
        session.execute(delete(DisplayToken).where(DisplayToken.tenant_id == tenant.id))
        session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
        session.execute(delete(User).where(User.tenant_id == tenant.id))
        session.execute(
            delete(AttendanceLocation).where(AttendanceLocation.tenant_id == tenant.id)
        )
        session.execute(delete(Tenant).where(Tenant.id == tenant.id))
        session.commit()


@pytest.fixture
def committed(engine: Engine) -> Iterator[Fixture]:
    _purge(engine, PROBE_SLUG)
    with Session(engine) as session:
        tenant = Tenant(name="Display Race Probe", slug=PROBE_SLUG)
        session.add(tenant)
        session.flush()

        location = AttendanceLocation(
            tenant_id=tenant.id, name="HQ", latitude=12.9716, longitude=77.5946
        )
        session.add(location)

        admin = User(
            tenant_id=tenant.id,
            employee_code="ADM-1",
            name="Admin",
            email=f"admin@{PROBE_SLUG}.com",
            password_hash="unused",
            role=UserRole.TENANT_ADMIN.value,
        )
        session.add(admin)
        session.flush()

        record, raw_token = display_service.create_display_token(
            session, tenant_id=tenant.id, created_by_user_id=admin.id, label="Lobby"
        )
        session.commit()

        fixture = Fixture(
            tenant_id=tenant.id,
            display_token_id=record.id,
            raw_token=raw_token,
            admin_id=admin.id,
        )

    try:
        yield fixture
    finally:
        _purge(engine, PROBE_SLUG)


def test_a_heartbeat_racing_a_revoke_never_authenticates_after_it_commits(
    engine: Engine, committed: Fixture
) -> None:
    session_revoke = Session(engine)
    session_heartbeat = Session(engine)
    b_entered = threading.Event()
    outcome: dict[str, object] = {}

    try:
        # A: revoke, held open (flush only) so its row lock is live but not
        # yet visible to a concurrent reader.
        record = session_revoke.scalar(
            select(DisplayToken).where(DisplayToken.id == committed.display_token_id)
        )
        assert record is not None
        display_service.revoke_display_token(
            session_revoke,
            tenant_id=committed.tenant_id,
            display_token_id=committed.display_token_id,
            actor_user_id=committed.admin_id,
        )
        session_revoke.flush()

        def run_heartbeat() -> None:
            b_entered.set()
            try:
                outcome["context"] = get_current_display(
                    session_heartbeat,
                    SimpleNamespace(credentials=committed.raw_token),  # type: ignore[arg-type]
                )
            except Exception as exc:  # noqa: BLE001 - the outcome under test
                outcome["context"] = exc
            session_heartbeat.commit()

        thread_b = threading.Thread(target=run_heartbeat, daemon=True)
        thread_b.start()
        assert b_entered.wait(timeout=10), "heartbeat thread never started"
        time.sleep(LOCK_WAIT_SECONDS)
        second_blocked = thread_b.is_alive()

        session_revoke.commit()
        thread_b.join(timeout=30)
        assert not thread_b.is_alive(), "heartbeat transaction deadlocked"
    finally:
        session_revoke.close()
        session_heartbeat.close()

    assert second_blocked, "no lock contention - the test proved nothing"
    # The heartbeat lost the race and reached the row only after the revoke
    # committed - it must see the revoked state, never a stale un-revoked read.
    assert isinstance(outcome["context"], Exception)
    assert getattr(outcome["context"], "status_code", None) == 401

    with Session(engine) as session:
        record = session.get(DisplayToken, committed.display_token_id)
        assert record is not None
        assert record.revoked_at is not None
        # The rejected heartbeat wrote nothing - `last_used_at` stays unset.
        assert record.last_used_at is None
