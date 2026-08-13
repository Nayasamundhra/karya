"""The single endpoint that exists in Phase 1."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    # Exactly this payload - no configuration or credentials leak out.
    assert response.json() == {"status": "ok"}
