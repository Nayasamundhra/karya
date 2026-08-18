"""Alembic environment.

The database URL is taken from the application settings (environment / .env)
rather than from ``alembic.ini``, so credentials are never committed. Set
``DATABASE_URL`` or the ``POSTGRES_*`` variables before running Alembic.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base

# Importing the models package registers every table on Base.metadata.
import app.models  # noqa: F401  (side-effecting import)

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is load-bearing, not tidiness. `fileConfig`
    # defaults to True, which disables every logger that already exists - and since
    # this module imports `app.core.config`, that includes all of Karya's. Any
    # process that runs Alembic in-process (the test suite does; a deployment hook
    # might) would afterwards emit no application logs at all, silently.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL to migrate.

    Precedence: programmatic override (``config.attributes["db_url"]``, used by
    the test suite), then the command line (``-x db_url=...``), then the
    application settings.
    """
    programmatic = config.attributes.get("db_url")
    if programmatic:
        return str(programmatic)
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override
    return settings.sqlalchemy_database_uri.get_secret_value()


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting to a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and run migrations in a transaction."""
    # Inject the URL here rather than storing it in alembic.ini.
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
