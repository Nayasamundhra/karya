"""Shared pytest fixtures.

The suite runs against a **real PostgreSQL** database, not SQLite: JSONB,
TIMESTAMPTZ, ``gen_random_uuid()`` and multi-column unique constraints must be
exercised against the engine that will run in production.

The test database (``<POSTGRES_DB>_test`` unless ``TEST_DATABASE_URL`` is set)
is created automatically if missing, and its schema is built by running the
Alembic migrations - so every test run also proves the migrations apply.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import (
    DEFAULT_GEOFENCE_RADIUS_METERS,
    AttendanceLocation,
    Tenant,
    User,
    UserRole,
    UserStatus,
)
from app.models.attendance_location import LOCATION_STATUS_ACTIVE
from app.services.auth.password import hash_password

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: Password used by `user_factory` unless a test overrides it.
DEFAULT_PASSWORD = "correct-horse-battery-staple"

#: The attendance-location coordinates used across the presence tests
#: (Bangalore, as in the specification's own examples).
OFFICE_LATITUDE = 12.9716
OFFICE_LONGITUDE = 77.5946

#: Metres per degree of latitude for this Earth model: R * radians(1).
#: Exact along a meridian, so a test can place a device a chosen distance away.
METERS_PER_DEGREE_LATITUDE = 111_194.93


def offset_north(latitude: float, meters: float) -> float:
    """Return ``latitude`` shifted ``meters`` northwards."""
    return latitude + meters / METERS_PER_DEGREE_LATITUDE


def _test_url() -> URL:
    return make_url(settings.sqlalchemy_test_database_uri.get_secret_value())


def _ensure_database_exists(url: URL) -> None:
    """Create the target database if it does not exist yet.

    ``CREATE DATABASE`` cannot run inside a transaction, hence AUTOCOMMIT, and
    it must be issued from a different database, hence ``postgres``.
    """
    admin_engine = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar_one_or_none()
            if exists is None:
                # The database name comes from configuration, never from a
                # request, and cannot be parameterised in DDL.
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin_engine.dispose()


def _alembic_config(url: URL) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # Consumed by alembic/env.py in preference to the application settings.
    config.attributes["db_url"] = url.render_as_string(hide_password=False)
    return config


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Session-wide engine bound to a freshly migrated test database."""
    url = _test_url()
    _ensure_database_exists(url)

    config = _alembic_config(url)
    # Rebuild from scratch so each run starts from a known state (and the
    # downgrade path stays exercised).
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    test_engine = create_engine(url, pool_pre_ping=True)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Per-test session whose work is always rolled back.

    The session joins an outer transaction using savepoints, so a test may call
    ``commit()`` (and recover from an ``IntegrityError``) while still leaving
    the database untouched afterwards.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Phase 2 - authentication fixtures
# ---------------------------------------------------------------------------


def make_get_db_override(session: Session) -> Callable[[], Iterator[Session]]:
    """Build a ``get_db`` replacement that yields ``session``.

    Must be a real generator function: FastAPI only applies its
    enter/exit handling to generator dependencies, so a lambda returning an
    iterator would inject the iterator itself instead of the session.
    """

    def _override() -> Iterator[Session]:
        yield session

    return _override


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """HTTP client whose requests share the test's rolled-back session.

    ``get_db`` is overridden so a route handler's ``session.commit()`` only
    releases a savepoint inside the test's outer transaction; nothing survives
    the test.
    """
    app.dependency_overrides[get_db] = make_get_db_override(db_session)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def tenant_factory(db_session: Session) -> Callable[..., Tenant]:
    """Create a persisted tenant."""

    def _make(slug: str = "acme", name: str | None = None) -> Tenant:
        tenant = Tenant(name=name or f"{slug.title()} Technologies", slug=slug)
        db_session.add(tenant)
        db_session.flush()
        return tenant

    return _make


@pytest.fixture
def user_factory(db_session: Session) -> Callable[..., User]:
    """Create a persisted user with a real Argon2id password hash."""

    def _make(
        tenant: Tenant,
        *,
        email: str = "staff@acme.com",
        password: str | None = DEFAULT_PASSWORD,
        employee_code: str = "EMP-001",
        name: str = "Rahul Sharma",
        role: UserRole = UserRole.STAFF,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> User:
        user = User(
            tenant_id=tenant.id,
            employee_code=employee_code,
            name=name,
            email=email,
            # None models a user who has never had a password set.
            password_hash=hash_password(password) if password is not None else None,
            role=role.value,
            status=status.value,
        )
        db_session.add(user)
        db_session.flush()
        return user

    return _make


@pytest.fixture
def location_factory(db_session: Session) -> Callable[..., AttendanceLocation]:
    """Create a persisted attendance location for a tenant.

    Defaults to the Bangalore coordinates used throughout the specification and
    the schema's own 150 m geofence.
    """

    def _make(
        tenant: Tenant,
        *,
        name: str = "Head Office",
        latitude: float = OFFICE_LATITUDE,
        longitude: float = OFFICE_LONGITUDE,
        geofence_radius_meters: int = DEFAULT_GEOFENCE_RADIUS_METERS,
        status: str = LOCATION_STATUS_ACTIVE,
    ) -> AttendanceLocation:
        location = AttendanceLocation(
            tenant_id=tenant.id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            geofence_radius_meters=geofence_radius_meters,
            status=status,
        )
        db_session.add(location)
        db_session.flush()
        return location

    return _make


@pytest.fixture
def login(client: TestClient) -> Callable[..., Response]:
    """Perform a login request and return the raw response."""

    def _login(
        tenant_slug: str, email: str, password: str = DEFAULT_PASSWORD
    ) -> Response:
        return client.post(
            "/api/v1/auth/login",
            json={
                "tenant_slug": tenant_slug,
                "email": email,
                "password": password,
            },
        )

    return _login


def auth_header(access_token: str) -> dict[str, str]:
    """Bearer header for an authenticated request."""
    return {"Authorization": f"Bearer {access_token}"}
