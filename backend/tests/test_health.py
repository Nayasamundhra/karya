"""The probes: liveness and readiness (Phases 1 and 7).

The distinction is the whole point of having two. Liveness must not depend on
PostgreSQL, because an orchestrator *kills* what fails liveness - so a database
blip would restart every healthy API process and turn a recoverable dependency
failure into an outage plus a restart storm. Readiness must depend on PostgreSQL,
because Karya cannot answer a single business request without it, and a load
balancer merely takes an unready instance out of rotation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db import session as db_session_module
from app.main import app
from app.middleware.request_context import REQUEST_ID_HEADER


@pytest.fixture
def probe_client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    # Exactly this payload - no configuration or credentials leak out.
    assert response.json() == {"status": "ok"}


def test_liveness_does_not_touch_the_database(
    probe_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserted by making any database access fail loudly.

    If ``/health`` ever grew a query, this test would fail rather than the property
    quietly eroding - and the property is what stops a database outage from becoming
    a rolling restart.
    """

    def explode() -> bool:
        raise AssertionError("liveness must not query the database")

    monkeypatch.setattr(db_session_module, "check_database_connectivity", explode)
    monkeypatch.setattr(db_session_module, "get_engine", explode)

    assert probe_client.get("/health").status_code == 200


def test_liveness_needs_no_credential(probe_client: TestClient) -> None:
    """A probe that needed a token could not be used by the infrastructure that
    needs it."""
    assert probe_client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def test_readiness_reports_ready_when_the_database_answers(
    probe_client: TestClient,
) -> None:
    response = probe_client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_reports_503_when_the_database_does_not(
    probe_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.api.probes.check_database_connectivity", lambda: False
    )

    response = probe_client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_readiness_exposes_no_infrastructure_detail(
    probe_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both probes are unauthenticated, so anything they return is public."""
    monkeypatch.setattr(
        "app.api.probes.check_database_connectivity", lambda: False
    )

    body = probe_client.get("/ready").text

    for leak in ("postgres", "psycopg", "5432", "localhost", "password", "karya_test"):
        assert leak not in body.lower(), leak


def test_a_database_failure_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``check_database_connectivity`` returns a boolean rather than propagating.

    The caller turns it into a bare 200 or 503; a raised ``OperationalError`` would
    become a 500, which an orchestrator reads as "broken" rather than "not ready".
    """
    from sqlalchemy.exc import OperationalError

    def failing_engine():  # noqa: ANN202 - a test double
        raise OperationalError("SELECT 1", {}, Exception("could not connect"))

    monkeypatch.setattr(db_session_module, "get_engine", failing_engine)

    assert db_session_module.check_database_connectivity() is False


def test_readiness_is_a_read_only_check(probe_client: TestClient) -> None:
    """It must be safe to call several times a second forever.

    A probe that wrote anything - a heartbeat row, an audit entry - would make the
    monitoring interval a load parameter.
    """
    from sqlalchemy import func, select

    from app.models import AttendanceEvent, AuditLog

    engine = db_session_module.get_engine()
    with engine.connect() as connection:
        before = (
            connection.execute(select(func.count()).select_from(AttendanceEvent)).scalar(),
            connection.execute(select(func.count()).select_from(AuditLog)).scalar(),
        )

    for _ in range(20):
        assert probe_client.get("/ready").status_code == 200

    with engine.connect() as connection:
        after = (
            connection.execute(select(func.count()).select_from(AttendanceEvent)).scalar(),
            connection.execute(select(func.count()).select_from(AuditLog)).scalar(),
        )

    assert before == after


# ---------------------------------------------------------------------------
# Both probes behave like the rest of the API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_are_hardened_and_traceable(probe_client: TestClient, path: str) -> None:
    response = probe_client.get(path)

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_sit_outside_the_api_version(probe_client: TestClient, path: str) -> None:
    """They describe the process, not the API contract, so they must not move or
    disappear when a new API version is introduced."""
    assert probe_client.get(path).status_code in {200, 503}
    assert probe_client.get(f"/api/v1{path}").status_code == 404


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_probes_are_documented(path: str) -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"][path]["get"]
    assert operation["tags"] == ["health"]
    assert operation["summary"]
    # No security requirement: both are deliberately unauthenticated.
    assert "security" not in operation


def test_readiness_documents_its_failure_status() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "503" in schema["paths"]["/ready"]["get"]["responses"]
