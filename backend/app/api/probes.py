"""Liveness and readiness probes.

Two endpoints rather than one, because they answer different questions and an
orchestrator does different things with the answers.

``/health`` asks *is this process alive?* and must never depend on anything
external. If liveness touched PostgreSQL, a brief database outage would make
Kubernetes (or a systemd watchdog, or an ECS health check) kill and restart every
API process - converting a recoverable dependency failure into a full outage, and
adding a restart storm on top of it at the exact moment the database is least able
to cope.

``/ready`` asks *can this process serve a request?* and therefore must depend on
PostgreSQL, because Karya cannot answer a single business request without it. A
load balancer removes an unready instance from rotation without killing it, so it
can rejoin as soon as the dependency returns.

Both live outside ``/api/v1``: they describe the process, not the API contract, so
they must not move or disappear when a new API version is introduced.

Neither is authenticated - a probe that needed a credential could not be used by
the infrastructure that needs it - so both are written on the assumption that
anything they return is public. Hence a fixed one-word payload and no version,
hostname, driver, timing or error detail.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.db.session import check_database_connectivity

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    responses={200: {"description": "The process is running"}},
)
def health() -> dict[str, str]:
    """Report that the process is running. Never touches the database."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness probe",
    responses={
        200: {"description": "Ready to serve traffic"},
        503: {"description": "Not ready - a required dependency is unavailable"},
    },
)
def ready(response: Response) -> dict[str, str]:
    """Report whether a trivial query against PostgreSQL succeeds."""
    if not check_database_connectivity():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}
