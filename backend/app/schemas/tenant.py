"""Tenant response and request schemas.

Scope is deliberately small. Tenant lifecycle is sensitive - creation, suspension
and deletion are operator concerns, not something a tenant administrator does to
their own tenant through the same API they use to manage staff. Billing, plans and
subscriptions do not exist in Karya at all yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.fields import PersonName


class TenantResponse(BaseModel):
    """The caller's own tenant."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime
    updated_at: datetime


class TenantUpdateRequest(BaseModel):
    """The only tenant field a tenant administrator may change.

    ``slug`` is excluded even though it is human-readable metadata: it is the
    tenant identifier every user types at login, so changing it would silently
    lock out an entire company. ``status`` is excluded because tenant suspension
    is an operator action, not a self-service one. ``id`` and the timestamps are
    not writable anywhere.
    """

    model_config = ConfigDict(extra="forbid")

    name: PersonName | None = None

    @model_validator(mode="after")
    def _require_a_change(self) -> TenantUpdateRequest:
        if self.name is None:
            raise ValueError("no updatable field supplied")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)
