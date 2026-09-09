"""Onboarding's two atomic single-attempt operations under concurrency.

As in the other `*_concurrency.py` modules, these commit real rows on
separate connections and force genuine overlap with a `threading.Barrier`
rather than hoping two near-simultaneous requests happen to race - a
sub-millisecond round trip does not reliably collide on its own.

* **A tenant slug is claimed by exactly one signup.** `create_tenant_with_admin`
  used to check uniqueness with a plain `SELECT` before inserting - a race two
  concurrent signups could both pass. It is now backed by the database's own
  `UNIQUE(slug)` constraint via a nested transaction (SAVEPOINT), the same
  pattern `app.services.users.service.create_user` uses for duplicate email.
* **A verification token is consumed by exactly one caller.** `verify_email`
  already used a single atomic `UPDATE ... WHERE consumed_at IS NULL
  ... RETURNING`, matching the QR-challenge single-use pattern - this adds the
  same real-race proof the QR suite (`test_presence_concurrency.py`) carries
  for that pattern, rather than leaving it as an unverified analogy.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.tokens import generate_opaque_token, hash_opaque_token
from app.models import AuditLog, Tenant, User
from app.models.email_verification_token import EmailVerificationToken
from app.services.onboarding import service as onboarding_service

PROBE_SLUG = "onboard-race-probe"


def _purge_tenant(engine: Engine, slug: str) -> None:
    with Session(engine) as session:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            return
        session.execute(
            delete(EmailVerificationToken).where(EmailVerificationToken.tenant_id == tenant.id)
        )
        session.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
        session.execute(delete(User).where(User.tenant_id == tenant.id))
        session.execute(delete(Tenant).where(Tenant.id == tenant.id))
        session.commit()


@pytest.fixture
def clean_slug(engine: Engine) -> Iterator[str]:
    _purge_tenant(engine, PROBE_SLUG)
    try:
        yield PROBE_SLUG
    finally:
        _purge_tenant(engine, PROBE_SLUG)


# ---------------------------------------------------------------------------
# Concurrent signup with the same slug
# ---------------------------------------------------------------------------


def test_two_simultaneous_signups_for_one_slug_yield_one_tenant(
    engine: Engine, clean_slug: str
) -> None:
    results: list[object] = [None, None]
    barrier = threading.Barrier(2, timeout=30)

    def attempt(index: int) -> None:
        with Session(engine) as session:
            barrier.wait()
            try:
                onboarding_service.create_tenant_with_admin(
                    session,
                    organization_name="Onboard Race Probe",
                    organization_slug=clean_slug,
                    admin_name=f"Admin {index}",
                    admin_email=f"admin{index}@{clean_slug}.com",
                    admin_password="correct-horse-battery-staple",
                )
                session.commit()
                results[index] = "created"
            except onboarding_service.SlugTakenError:
                session.rollback()
                results[index] = "SlugTakenError"

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert results.count("created") == 1
    assert results.count("SlugTakenError") == 1

    with Session(engine) as session:
        stored = session.scalar(
            select(func.count()).select_from(Tenant).where(Tenant.slug == clean_slug)
        )
    assert stored == 1, f"duplicate tenant created for one slug: {results}"


# ---------------------------------------------------------------------------
# Concurrent redemption of one verification token
# ---------------------------------------------------------------------------


@pytest.fixture
def unverified_admin(engine: Engine, clean_slug: str) -> Iterator[tuple[uuid.UUID, str]]:
    """A committed, INACTIVE admin with one valid, unconsumed token."""
    raw_token = generate_opaque_token()
    with Session(engine) as session:
        onboarding_service.create_tenant_with_admin(
            session,
            organization_name="Onboard Race Probe",
            organization_slug=clean_slug,
            admin_name="Ada Lovelace",
            admin_email=f"ada@{clean_slug}.com",
            admin_password="correct-horse-battery-staple",
        )
        session.commit()

        admin = session.scalar(select(User).where(User.email == f"ada@{clean_slug}.com"))
        assert admin is not None
        # Overwrite the real (unrecoverable, already-hashed) onboarding token
        # with one this test controls the raw value of.
        token = session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.user_id == admin.id)
        )
        assert token is not None
        token.token_hash = hash_opaque_token(raw_token)
        session.commit()
        admin_id = admin.id

    yield admin_id, raw_token


def test_eight_simultaneous_redemptions_of_one_token_yield_one_success(
    engine: Engine, unverified_admin: tuple[uuid.UUID, str]
) -> None:
    """Eight independent transactions consume the same link; exactly one wins.

    Mirrors `test_presence_concurrency.py::test_repeated_attempts_yield_exactly_one_success`
    for the QR single-use pattern - `verify_email` is the same atomic
    `UPDATE ... RETURNING` shape.
    """
    admin_id, raw_token = unverified_admin
    results: list[bool] = [False] * 8
    barrier = threading.Barrier(8, timeout=30)

    def attempt(index: int) -> None:
        with Session(engine) as session:
            barrier.wait()
            try:
                onboarding_service.verify_email(session, raw_token=raw_token)
                session.commit()
                results[index] = True
            except onboarding_service.VerificationError:
                session.rollback()
                results[index] = False

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert results.count(True) == 1, f"expected exactly one winner: {results}"
    assert results.count(False) == 7

    with Session(engine) as session:
        admin = session.get(User, admin_id)
        assert admin is not None
        assert admin.status == "ACTIVE"

        verified_count = session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.target_id == admin_id,
                AuditLog.action == onboarding_service.ACTION_EMAIL_VERIFIED,
            )
        )
    # One winner, one audit row - not eight racing writers each logging a win.
    assert verified_count == 1
