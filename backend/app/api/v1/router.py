"""Aggregate router for API v1.

The version prefix lives here rather than in ``main.py`` so that a version is one
self-contained thing: its routers and the path they mount at are declared together.
Adding ``/api/v2`` later means a sibling ``app/api/v2/router.py`` exporting its own
``API_V2_PREFIX`` and one more ``include_router`` call - v1's URLs, schemas and
handlers are untouched, which is the only property that makes versioning worth
having.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from app.api.v1 import attendance, auth, display, onboarding, presence, tenant, users

#: Mount point for every v1 business endpoint. The probes (`/health`, `/ready`)
#: sit outside it on purpose: they describe the *process*, not the API contract, so
#: they must not move or disappear when a new API version does.
API_V1_PREFIX: Final[str] = "/api/v1"

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(onboarding.router)
api_router.include_router(presence.router)
api_router.include_router(attendance.router)
api_router.include_router(users.router)
api_router.include_router(tenant.router)
api_router.include_router(display.router)
api_router.include_router(display.self_router)
