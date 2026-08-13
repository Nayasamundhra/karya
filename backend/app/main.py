"""Karya FastAPI application.

Phase 2 exposes the authentication endpoints under ``/api/v1`` plus the Phase 1
liveness probe. Business routers (attendance, locations, QR) arrive later.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

API_V1_PREFIX = "/api/v1"

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    summary="Multi-tenant staff attendance and presence verification platform.",
)

# CORS is opt-in per origin, read from CORS_ALLOWED_ORIGINS. There is no
# wildcard fallback: with credentialed requests a wildcard is both invalid per
# the CORS spec and unsafe, and `Settings` rejects one outright. An empty list
# means no browser origin is permitted, which is the safe default for a
# backend-only deployment.
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

app.include_router(api_router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe.

    Returns a static payload only - it deliberately exposes no configuration,
    version or database connectivity detail.
    """
    return {"status": "ok"}
