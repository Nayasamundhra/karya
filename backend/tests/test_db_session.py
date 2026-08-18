"""Engine, pool and session lifecycle (Phase 7).

The pool is configuration that has no visible symptom until production: too small
and requests queue, too large and PostgreSQL runs out of backends, no recycling and
a proxy hands back a dead connection. None of that shows up in a functional test,
so it is asserted directly against the constructed engine - which ``create_engine``
builds without connecting, so these tests are cheap and deterministic.

The session tests cover the property that *does* have a symptom, and a nasty one: a
failed request must not leave a half-applied transaction on a pooled connection for
the next request to inherit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import (
    _connect_args,
    check_database_connectivity,
    dispose_engine,
    get_db,
    get_engine,
    get_sessionmaker,
)


# ---------------------------------------------------------------------------
# Pool configuration
# ---------------------------------------------------------------------------


def test_the_pool_is_sized_from_configuration() -> None:
    """Every knob is tunable per deployment, because the right size depends on
    PostgreSQL's ``max_connections`` and on how many instances are running."""
    pool = get_engine().pool

    assert pool.size() == settings.db_pool_size
    assert pool._max_overflow == settings.db_max_overflow
    assert pool._timeout == settings.db_pool_timeout_seconds
    assert pool._recycle == settings.db_pool_recycle_seconds


def test_the_defaults_are_conservative() -> None:
    """A large pool does not make a saturated database faster - it moves the queue
    from the application, where it is bounded and visible, into the server."""
    assert settings.db_pool_size <= 10
    assert settings.db_pool_size + settings.db_max_overflow <= 25


def test_connections_are_pre_pinged_and_recycled() -> None:
    """Both defend against the same failure: a connection that looks open and is not.

    Pre-ping catches it at checkout; recycling avoids reaching that point by
    retiring connections before an idle proxy or managed-database timeout does.
    """
    assert get_engine().pool._pre_ping is True
    assert 0 < settings.db_pool_recycle_seconds <= 3_600


def test_bound_parameters_are_hidden_from_exception_messages() -> None:
    """Not a debugging preference - a requirement.

    A ``users`` INSERT binds ``password_hash`` as a parameter, and SQLAlchemy renders
    bound parameters into exception messages, which reach log files. The structured
    audit log carries the business context instead.
    """
    assert get_engine().hide_parameters is True


def test_sql_is_never_echoed() -> None:
    """Statements can contain sensitive values."""
    assert get_engine().echo is False


def test_server_side_timeouts_are_applied_per_connection() -> None:
    """``statement_timeout`` bounds a runaway query; ``lock_timeout`` bounds the
    ``FOR UPDATE`` waits that attendance and last-admin protection rely on.

    Without them a stuck transaction holds its pool slot until the pool is exhausted
    and every request fails - one wedged statement becoming a full outage.
    """
    args = _connect_args()

    assert args["connect_timeout"] == settings.db_connect_timeout_seconds
    assert f"statement_timeout={settings.db_statement_timeout_ms}" in args["options"]
    assert f"lock_timeout={settings.db_lock_timeout_ms}" in args["options"]


def test_a_lock_timeout_is_far_above_the_expected_wait() -> None:
    """Karya's attendance path serialises on a row lock deliberately.

    The expected wait is milliseconds, so the timeout must be orders of magnitude
    larger - otherwise two colleagues checking in at once would see a failure.
    """
    assert settings.db_lock_timeout_ms >= 1_000
    assert settings.db_lock_timeout_ms <= settings.db_statement_timeout_ms


def test_timeouts_can_be_disabled_by_setting_them_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some managed platforms set these globally and would rather we did not."""
    monkeypatch.setattr(settings, "db_statement_timeout_ms", 0)
    monkeypatch.setattr(settings, "db_lock_timeout_ms", 0)

    args = _connect_args()

    assert "options" not in args
    assert args["connect_timeout"] == settings.db_connect_timeout_seconds


def test_the_timeouts_actually_reach_the_server() -> None:
    """Asserting the connect arguments is not enough: they have to take effect.

    Read back from the live connection, so a typo in the ``options`` string is caught
    here rather than discovered when a query fails to time out.
    """
    # `pg_settings.setting` reports the raw value in the setting's own unit (ms
    # for both of these). `SHOW` would render it human-readably - PostgreSQL turns
    # 15000ms into "15s" - which is the same value in a form that is awkward to
    # compare against.
    with get_engine().connect() as connection:
        applied = dict(
            connection.execute(
                text(
                    "SELECT name, setting FROM pg_settings "
                    "WHERE name IN ('statement_timeout', 'lock_timeout')"
                )
            ).all()
        )

    assert int(applied["statement_timeout"]) == settings.db_statement_timeout_ms
    assert int(applied["lock_timeout"]) == settings.db_lock_timeout_ms


# ---------------------------------------------------------------------------
# Engine and session identity
# ---------------------------------------------------------------------------


def test_there_is_exactly_one_engine_per_process() -> None:
    """A fresh engine per call would mean a fresh pool per call - unbounded
    connections, and pre-ping and recycling doing nothing."""
    assert get_engine() is get_engine()
    assert get_sessionmaker() is get_sessionmaker()
    assert get_sessionmaker().kw["bind"] is get_engine()


def test_sessions_do_not_autoflush_or_expire_on_commit() -> None:
    """Both matter to the service layer.

    ``autoflush=False`` keeps a read from silently emitting a partially-built
    INSERT; ``expire_on_commit=False`` lets a route read the object it just
    committed without a second SELECT - which is how the attendance handlers return
    the row they wrote.
    """
    factory = get_sessionmaker()

    assert factory.kw["autoflush"] is False
    assert factory.kw["expire_on_commit"] is False


def test_the_database_url_is_never_exposed_as_a_plain_string() -> None:
    """The URL embeds the password, so it is a ``SecretStr`` everywhere but the one
    deliberate call that builds the engine."""
    assert "***" in settings.safe_database_uri
    assert settings.postgres_password.get_secret_value() not in settings.safe_database_uri


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_get_db_closes_the_session() -> None:
    generator = get_db()
    session = next(generator)
    session.execute(text("SELECT 1"))
    assert session.in_transaction()

    with pytest.raises(StopIteration):
        next(generator)

    # `close()` releases the connection back to the pool and ends the transaction.
    # (`Session.is_active` is not the check: in SQLAlchemy 2.x it means "not in a
    # failed transaction", and it stays True on a closed session.)
    assert not session.in_transaction()


def test_get_db_rolls_back_when_the_caller_raises() -> None:
    """The property with the nastiest failure mode.

    Without the rollback, a request that raised mid-transaction returns its
    connection to the pool with uncommitted work on it, and the next request to
    check that connection out inherits the mess.
    """
    generator = get_db()
    session = next(generator)
    session.execute(text("SELECT 1"))
    assert session.in_transaction()

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("the route blew up"))

    assert not session.in_transaction()


def test_the_rollback_is_explicit_and_only_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing a session happens to roll back, so the explicit call could look
    redundant. It is not, and this pins which calls happen in which order.

    On the happy path nothing is rolled back - the caller owns the transaction, and
    a rollback here would undo a route that committed deliberately.
    """
    calls: list[str] = []

    class RecordingSession:
        def rollback(self) -> None:
            calls.append("rollback")

        def close(self) -> None:
            calls.append("close")

    monkeypatch.setattr(
        "app.db.session.get_sessionmaker", lambda: (lambda: RecordingSession())
    )

    # Happy path: closed, never rolled back.
    generator = get_db()
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)
    assert calls == ["close"]

    # Failure path: rolled back first, then closed.
    calls.clear()
    generator = get_db()
    next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("the route blew up"))
    assert calls == ["rollback", "close"]


def test_connectivity_check_is_true_against_a_reachable_database() -> None:
    assert check_database_connectivity() is True


def test_connectivity_check_swallows_only_database_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configuration bug must not be reported as "the database is down"."""

    def broken():  # noqa: ANN202 - a test double
        raise ValueError("this is a programming error, not an outage")

    monkeypatch.setattr("app.db.session.get_engine", broken)

    with pytest.raises(ValueError):
        check_database_connectivity()


def test_connectivity_check_reports_false_on_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEngine:
        def connect(self):  # noqa: ANN202 - a test double
            raise SQLAlchemyError("connection refused")

    monkeypatch.setattr("app.db.session.get_engine", lambda: FailingEngine())

    assert check_database_connectivity() is False


class _UncreatedEngine:
    """Stands in for ``get_engine`` before anything has asked for an engine.

    Mimics the two things ``dispose_engine`` uses: the ``lru_cache`` introspection
    and being callable. Calling it is the mistake being guarded against, so it
    records the attempt.
    """

    def __init__(self) -> None:
        self.called = False

    @staticmethod
    def cache_info() -> object:
        return type("Info", (), {"currsize": 0})()

    def __call__(self) -> object:  # pragma: no cover - failing the test is the point
        self.called = True
        raise AssertionError("dispose_engine created an engine it should not have")


def test_disposing_an_uncreated_engine_creates_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown must not open a connection pool purely in order to close it.

    Otherwise a process that never touched the database would connect to it on the
    way out, and would fail to shut down cleanly whenever the database is the thing
    that is unavailable.
    """
    stub = _UncreatedEngine()
    monkeypatch.setattr("app.db.session.get_engine", stub)

    dispose_engine()

    assert stub.called is False


def test_disposing_a_created_engine_closes_the_pool() -> None:
    """The other half: a pool that was created really is closed.

    Disposal is safe to call on a live engine - SQLAlchemy replaces the pool rather
    than invalidating the engine - so a later request simply reconnects.
    """
    engine = get_engine()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert engine.pool.checkedin() >= 1

    dispose_engine()

    assert engine.pool.checkedin() == 0
    # Still usable, so disposal at shutdown cannot break a process that keeps going.
    assert check_database_connectivity() is True
