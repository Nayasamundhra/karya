"""Engine and session factory.

The engine is created lazily so that merely importing this module (for example
by Alembic, or by a unit test that supplies its own engine) does not require a
reachable database.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine."""
    return create_engine(
        settings.sqlalchemy_database_uri.get_secret_value(),
        pool_pre_ping=True,
        # Never echo SQL by default: statements can contain sensitive values.
        echo=False,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Iterator[Session]:
    """Yield a database session and always close it.

    Intended as a FastAPI dependency in later phases. The caller owns the
    transaction: nothing is committed implicitly.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
