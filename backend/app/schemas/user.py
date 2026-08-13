"""User response schemas.

``UserResponse`` is an explicit allowlist of fields. It is built by naming each
attribute rather than by excluding sensitive ones, so a column added to the ORM
model in a later phase can never leak by default - ``password_hash`` included.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponse(BaseModel):
    """The authenticated user, as returned by ``GET /api/v1/auth/me``.

    Deliberately excludes ``password_hash`` and every other authentication
    artefact. ``created_at``/``updated_at`` are omitted too - nothing needs them
    yet, and the narrower the response, the less there is to leak.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    employee_code: str
    name: str
    email: EmailStr
    role: str
    status: str
