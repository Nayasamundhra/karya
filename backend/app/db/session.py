"""Engine and session factory.

The engine is created lazily so that merely importing this module (for example
by Alembic, or by a unit test that supplies its own engine) does not require a
reachable database.

## Pool sizing

Every API process holds up to ``DB_POOL_SIZE + DB_MAX_OVERFLOW`` server
connections. The defaults are small on purpose - PostgreSQL's ``max_connections``
is a shared budget, and each backend costs real memory, so the arithmetic that
matters is:

    instances x workers x (pool_size + max_overflow)  <  max_connections - headroom

A bigger pool does not make a saturated database faster; it moves the queue out of
the application, where it is visible and bounded, into the server, where it is
neither. ``docs/PRODUCTION.md`` works the numbers through for a concrete
deployment.

## Server-side timeouts

``statement_timeout`` and ``lock_timeout`` are set per connection rather than left
to the server default of "wait forever". Karya's attendance and last-admin paths
deliberately block on ``SELECT ... FOR UPDATE``; the expected wait is milliseconds,
so a wait measured in seconds means a transaction is stuck, and failing that one
request is better than holding its pool slot until the pool is exhausted and every
request fails.

``hide_parameters=True`` is not a debugging inconvenience but a requirement: a
``users`` INSERT binds ``password_hash`` as a parameter, and SQLAlchemy renders
bound parameters into exception messages. Those messages reach log files.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def _connect_args() -> dict[str, str | int]:
    """psycopg connection arguments derived from settings.

    ``options`` is passed through to the server as startup parameters, which is
    how a per-connection ``statement_timeout``/``lock_timeout`` is applied without
    issuing an extra ``SET`` on every checkout.
    """
    args: dict[str, str | int] = {
        "connect_timeout": settings.db_connect_timeout_seconds
    }
    options = []
    if settings.db_statement_timeout_ms:
        options.append(f"-c statement_timeout={settings.db_statement_timeout_ms}")
    if settings.db_lock_timeout_ms:
        options.append(f"-c lock_timeout={settings.db_lock_timeout_ms}")
    if options:
        args["options"] = " ".join(options)
    return args


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine."""
    return create_engine(
        settings.sqlalchemy_database_uri.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        # Recycle before an idle proxy, firewall or managed-database timeout can
        # hand back a connection that looks open and is not.
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args=_connect_args(),
        # Never echo SQL by default: statements can contain sensitive values.
        echo=False,
        # See the module docstring: bound parameters include password hashes.
        hide_parameters=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def dispose_engine() -> None:
    """Close every pooled connection, if an engine was ever created.

    Called from the application's shutdown handler. The cache is inspected rather
    than calling :func:`get_engine`, because a process that never touched the
    database must not open a connection pool purely in order to close it.
    """
    if get_engine.cache_info().currsize == 0:
        return
    get_engine().dispose()
    logger.info("database_pool_disposed", extra={"event": "database_pool_disposed"})


def get_db() -> Iterator[Session]:
    """Yield a database session, rolling back on failure and always closing.

    The caller owns the transaction: nothing is committed implicitly. The explicit
    rollback matters for correctness, not just tidiness - a route that raises
    partway through (or a handler that turns an exception into a 4xx) must not
    leave a half-applied transaction on a pooled connection for the next request
    to inherit.
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connectivity() -> bool:
    """Whether a trivial query succeeds against the configured database.

    Used by the readiness probe. Deliberately returns a boolean rather than
    raising or reporting *why*: the caller turns this into a bare 200 or 503, and
    a probe response that described the database error would publish
    infrastructure detail to anyone who can reach the port.
    """
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning(
            "database_unreachable",
            extra={"event": "database_unreachable"},
            exc_info=True,
        )
        return False
    return True
