"""Last-admin and duplicate-email invariants under concurrency (spec 45-49, 71, 72).

As in the earlier concurrency modules, these commit real rows on separate
connections and force a deterministic interleaving. Releasing threads together
does not reliably open the window - each request is a sub-millisecond round trip -
so each guarantee is paired with a test asserting the *naive* implementation
breaks under the identical harness. If that ever stops failing, the harness has
gone slack and the real test would pass regardless of the code.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import Engine, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AttendanceEvent,
    AuditLog,
    QRChallenge,
    RefreshToken,
    Tenant,
    User,
    UserRole,
    UserStatus,
)
from app.services.auth.password import hash_password
from app.services.users import errors
from app.services.users import service as users_service
from tests.conftest import DEFAULT_PASSWORD

PROBE_SLUG = "user-race-probe"
LOCK_WAIT_SECONDS = 1.0


@dataclass(frozen=True)
class Fixture:
    tenant_id: uuid.UUID
    admin_ids: tuple[uuid.UUID, ...]
    staff_id: uuid.UUID


def _purge(engine: Engine, tenant_id: uuid.UUID) -> None:
    with Session(engine) as session:
        for model in (QRChallenge, AuditLog, RefreshToken, AttendanceEvent):
            session.execute(delete(model).where(model.tenant_id == tenant_id))
        session.execute(delete(User).where(User.tenant_id == tenant_id))
        session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        session.commit()


@pytest.fixture
def committed(engine: Engine) -> Iterator[Fixture]:
    """A committed tenant with two active admins and one staff member."""
    with Session(engine) as session:
        stale = session.scalar(select(Tenant).where(Tenant.slug == PROBE_SLUG))
        stale_id = stale.id if stale is not None else None
    if stale_id is not None:
        _purge(engine, stale_id)

    with Session(engine) as session:
        tenant = Tenant(name="User Race Probe", slug=PROBE_SLUG)
        session.add(tenant)
        session.flush()

        admins = []
        for index in (1, 2):
            admin = User(
                tenant_id=tenant.id,
                employee_code=f"ADM-{index}",
                name=f"Admin {index}",
                email=f"admin{index}@{PROBE_SLUG}.com",
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole.TENANT_ADMIN.value,
            )
            session.add(admin)
            admins.append(admin)
        staff = User(
            tenant_id=tenant.id,
            employee_code="EMP-1",
            name="Rahul",
            email=f"rahul@{PROBE_SLUG}.com",
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.STAFF.value,
        )
        session.add(staff)
        session.commit()

        fixture = Fixture(
            tenant_id=tenant.id,
            admin_ids=tuple(a.id for a in admins),
            staff_id=staff.id,
        )

    try:
        yield fixture
    finally:
        _purge(engine, fixture.tenant_id)


@dataclass
class Interleaving:
    first: object
    second: object
    second_blocked: bool


def interleave(
    engine: Engine, operation: Callable[[Session, int], object]
) -> Interleaving:
    """Run ``operation`` twice with a forced overlap; B must block on A's locks."""
    session_a = Session(engine)
    session_b = Session(engine)
    outcome: dict[str, object] = {}
    b_entered = threading.Event()

    def capture(session: Session, index: int) -> object:
        try:
            return operation(session, index)
        except Exception as exc:  # noqa: BLE001 - the outcome under test
            return exc

    try:
        first = capture(session_a, 0)
        session_a.flush()

        def run_second() -> None:
            b_entered.set()
            outcome["value"] = capture(session_b, 1)
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


def active_admin_count(engine: Engine, tenant_id: uuid.UUID) -> int:
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == tenant_id,
                User.role == UserRole.TENANT_ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
            )
        ) or 0


# ---------------------------------------------------------------------------
# 45-48. Sequential last-admin protection
# ---------------------------------------------------------------------------


def test_a_tenant_with_two_admins_can_lose_one(
    engine: Engine, committed: Fixture
) -> None:
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[0])
        users_service.set_user_status(
            session,
            tenant_id=committed.tenant_id,
            actor=actor,
            user_id=committed.admin_ids[1],
            status=UserStatus.INACTIVE,
        )
        session.commit()

    assert active_admin_count(engine, committed.tenant_id) == 1


def test_the_final_admin_cannot_be_deactivated(
    engine: Engine, committed: Fixture
) -> None:
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[0])
        users_service.set_user_status(
            session, tenant_id=committed.tenant_id, actor=actor,
            user_id=committed.admin_ids[1], status=UserStatus.INACTIVE,
        )
        session.commit()

    # admin_ids[0] is now the only active admin. Another admin cannot be
    # conjured, so the staff member attempts it via the service as the actor.
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[1])  # inactive, but the actor
        with pytest.raises(errors.LastAdminError):
            users_service.set_user_status(
                session, tenant_id=committed.tenant_id, actor=actor,
                user_id=committed.admin_ids[0], status=UserStatus.INACTIVE,
            )
        session.rollback()

    assert active_admin_count(engine, committed.tenant_id) == 1


def test_the_final_admin_cannot_be_demoted(
    engine: Engine, committed: Fixture
) -> None:
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[0])
        users_service.change_user_role(
            session, tenant_id=committed.tenant_id, actor=actor,
            user_id=committed.admin_ids[1], new_role=UserRole.STAFF,
        )
        session.commit()
    assert active_admin_count(engine, committed.tenant_id) == 1

    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[1])
        with pytest.raises(errors.LastAdminError):
            users_service.change_user_role(
                session, tenant_id=committed.tenant_id, actor=actor,
                user_id=committed.admin_ids[0], new_role=UserRole.STAFF,
            )
        session.rollback()

    assert active_admin_count(engine, committed.tenant_id) == 1


def test_promoting_to_admin_is_never_blocked(
    engine: Engine, committed: Fixture
) -> None:
    """The invariant guards against losing admins, not against gaining them."""
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[0])
        users_service.change_user_role(
            session, tenant_id=committed.tenant_id, actor=actor,
            user_id=committed.staff_id, new_role=UserRole.TENANT_ADMIN,
        )
        session.commit()

    assert active_admin_count(engine, committed.tenant_id) == 3


# ---------------------------------------------------------------------------
# 49. Concurrent last-admin removal
# ---------------------------------------------------------------------------


def test_two_simultaneous_demotions_cannot_remove_both_admins(
    engine: Engine, committed: Fixture
) -> None:
    """The core invariant: a tenant must never end up with zero admins."""

    def demote(session: Session, index: int) -> object:
        actor = session.get(User, committed.staff_id)
        return users_service.change_user_role(
            session,
            tenant_id=committed.tenant_id,
            actor=actor,
            user_id=committed.admin_ids[index],
            new_role=UserRole.STAFF,
        )

    result = interleave(engine, demote)

    assert result.second_blocked, "no lock contention - the test proved nothing"
    assert not isinstance(result.first, Exception)
    assert isinstance(result.second, errors.LastAdminError)
    assert active_admin_count(engine, committed.tenant_id) == 1


def test_two_simultaneous_deactivations_cannot_remove_both_admins(
    engine: Engine, committed: Fixture
) -> None:
    def deactivate(session: Session, index: int) -> object:
        actor = session.get(User, committed.staff_id)
        return users_service.set_user_status(
            session,
            tenant_id=committed.tenant_id,
            actor=actor,
            user_id=committed.admin_ids[index],
            status=UserStatus.INACTIVE,
        )

    result = interleave(engine, deactivate)

    assert result.second_blocked
    assert not isinstance(result.first, Exception)
    assert isinstance(result.second, errors.LastAdminError)
    assert active_admin_count(engine, committed.tenant_id) == 1


def test_a_naive_count_check_would_remove_both_admins(
    engine: Engine, committed: Fixture
) -> None:
    """Guards the two tests above from becoming vacuous.

    A ``SELECT COUNT(*)`` with no locking lets both transactions observe two
    admins and both proceed - which is precisely the production hazard the row
    lock exists to prevent.
    """

    def naive_demote(session: Session, index: int) -> object:
        target_id = committed.admin_ids[index]
        count = session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.tenant_id == committed.tenant_id,
                User.role == UserRole.TENANT_ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
            )
        )
        if count <= 1:
            raise errors.LastAdminError
        target = session.get(User, target_id)
        target.role = UserRole.STAFF.value
        session.flush()
        return target

    result = interleave(engine, naive_demote)

    assert not isinstance(result.first, Exception)
    # Both "succeed", leaving the tenant with no administrator at all.
    assert not isinstance(result.second, Exception)
    assert active_admin_count(engine, committed.tenant_id) == 0


# ---------------------------------------------------------------------------
# 33, 71. Duplicate email race
# ---------------------------------------------------------------------------


def test_two_simultaneous_creations_of_one_email_yield_one_user(
    engine: Engine, committed: Fixture
) -> None:
    """Uniqueness is the database's job, so a check-then-insert cannot slip through."""
    email = f"newhire@{PROBE_SLUG}.com"
    results: list[object] = [None, None]
    barrier = threading.Barrier(2, timeout=30)

    def attempt(index: int) -> None:
        with Session(engine) as session:
            actor = session.get(User, committed.admin_ids[0])
            barrier.wait()
            try:
                users_service.create_user(
                    session,
                    tenant_id=committed.tenant_id,
                    actor=actor,
                    email=email,
                    password=DEFAULT_PASSWORD,
                    name="New Hire",
                    employee_code=f"NEW-{index}",
                )
                session.commit()
                results[index] = "created"
            except (errors.EmailAlreadyExistsError, IntegrityError) as exc:
                session.rollback()
                results[index] = type(exc).__name__

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    with Session(engine) as session:
        stored = session.scalar(
            select(func.count()).select_from(User)
            .where(User.tenant_id == committed.tenant_id, User.email == email)
        )

    assert stored == 1, f"duplicate created: {results}"
    assert results.count("created") == 1
    assert "EmailAlreadyExistsError" in results


def test_a_conflicting_creation_leaves_no_audit_row(
    engine: Engine, committed: Fixture
) -> None:
    """Business mutation and audit row commit together, or neither does."""
    email = f"conflict@{PROBE_SLUG}.com"
    with Session(engine) as session:
        actor = session.get(User, committed.admin_ids[0])
        users_service.create_user(
            session, tenant_id=committed.tenant_id, actor=actor, email=email,
            password=DEFAULT_PASSWORD, name="First", employee_code="C-1",
        )
        session.commit()

    with Session(engine) as session:
        before = session.scalar(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.tenant_id == committed.tenant_id)
        )
        actor = session.get(User, committed.admin_ids[0])
        with pytest.raises(errors.EmailAlreadyExistsError):
            users_service.create_user(
                session, tenant_id=committed.tenant_id, actor=actor, email=email,
                password=DEFAULT_PASSWORD, name="Second", employee_code="C-2",
            )
        session.rollback()

    with Session(engine) as session:
        after = session.scalar(
            select(func.count()).select_from(AuditLog)
            .where(AuditLog.tenant_id == committed.tenant_id)
        )
        users = session.scalar(
            select(func.count()).select_from(User)
            .where(User.tenant_id == committed.tenant_id, User.email == email)
        )

    assert after == before
    assert users == 1
