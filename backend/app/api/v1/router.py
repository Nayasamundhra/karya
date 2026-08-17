"""Aggregate router for API v1.

Later phases add their routers here; each keeps its own prefix and tags.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import attendance, auth, presence, tenant, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(presence.router)
api_router.include_router(attendance.router)
api_router.include_router(users.router)
api_router.include_router(tenant.router)
