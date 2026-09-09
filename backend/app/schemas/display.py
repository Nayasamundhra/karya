"""Request/response schemas for managing office-display (kiosk) tokens.

See `app.models.display_token` and `app.api.display_deps` for what a display
token actually is. The raw token is returned exactly once, on creation - a
listing never includes it, the same convention `RefreshToken`/access tokens
use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DisplayTokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: A human label the admin chose, e.g. "Reception tablet" - shown back to
    #: them when listing/revoking. Not security-relevant.
    label: str = Field(min_length=1, max_length=255)


class DisplayTokenCreateResponse(BaseModel):
    """Returned once, on creation. The raw token is never retrievable again."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    label: str
    token: str
    created_at: datetime


class DisplayTokenResponse(BaseModel):
    """One row in the listing - never the raw token."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class DisplayTokenListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DisplayTokenResponse]
