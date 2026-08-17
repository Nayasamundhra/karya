"""User response schemas.

``UserResponse`` is an explicit allowlist of fields. It is built by naming each
attribute rather than by excluding sensitive ones, so a column added to the ORM
model in a later phase can never leak by default - ``password_hash`` included.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator

from app.models.user import UserRole
from app.schemas.fields import (
    EmployeeCode,
    NormalizedEmail,
    PersonName,
    PlainPassword,
)


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


class UserDetailResponse(UserResponse):
    """A user as returned by the management endpoints.

    Extends :class:`UserResponse` with lifecycle timestamps, which an
    administrator needs to see. Still an explicit allowlist - it inherits the
    named fields rather than serialising the ORM object, so a column added later
    cannot leak.
    """

    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------
#
# Every request model below sets `extra="forbid"`. That is the security boundary:
# `tenant_id`, `password_hash`, `created_at`, `updated_at`, `id` and - where not
# explicitly permitted - `role` and `status` are simply not declared, so an
# attempt to send one is a loud 422 rather than a field quietly ignored. Nothing
# in the service layer reads attributes generically off a request body, so there
# is no second path by which a privileged field could be reached.


class UserCreateRequest(BaseModel):
    """Fields a tenant administrator may supply when creating a user.

    ``tenant_id`` is absent by design - the tenant comes from the authenticated
    administrator, so a user can only ever be created inside the caller's own
    tenant.
    """

    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail
    password: PlainPassword
    name: PersonName
    employee_code: EmployeeCode
    #: Restricted to the roles a tenant may assign; SUPER_ADMIN is not one of
    #: them, so tenant administration cannot mint platform access.
    role: UserRole = UserRole.STAFF

    @model_validator(mode="after")
    def _reject_platform_role(self) -> UserCreateRequest:
        if self.role == UserRole.SUPER_ADMIN:
            raise ValueError("SUPER_ADMIN cannot be assigned within a tenant")
        return self


class UserUpdateRequest(BaseModel):
    """Profile fields a tenant administrator may change.

    Deliberately excludes ``role`` and ``status``: those are lifecycle and
    privilege changes with their own endpoints, their own authorization and their
    own audit actions. Folding them into a generic update would make a privilege
    change indistinguishable from a typo correction in the audit trail.

    PATCH semantics: every field is optional and only what is sent is written.
    """

    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail | None = None
    name: PersonName | None = None
    employee_code: EmployeeCode | None = None

    def changes(self) -> dict[str, Any]:
        """The supplied fields only, so absent ones stay untouched."""
        return self.model_dump(exclude_unset=True, exclude_none=True)


class SelfUpdateRequest(BaseModel):
    """Profile fields a user may change about themselves.

    Narrower than the administrator's version: no email, because it is the login
    identity - changing it unilaterally is how somebody locks themselves out, and
    it belongs to the tenant's administration. No employee code either, since the
    tenant assigns it.
    """

    model_config = ConfigDict(extra="forbid")

    name: PersonName | None = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)


class RoleUpdateRequest(BaseModel):
    """A role change, on its own dedicated endpoint."""

    model_config = ConfigDict(extra="forbid")

    role: UserRole

    @model_validator(mode="after")
    def _reject_platform_role(self) -> RoleUpdateRequest:
        if self.role == UserRole.SUPER_ADMIN:
            raise ValueError("SUPER_ADMIN cannot be assigned within a tenant")
        return self


class PasswordChangeRequest(BaseModel):
    """A self-service password change.

    No user id: the account is always the authenticated caller, so there is no
    field through which an administrator could set someone else's password.
    """

    model_config = ConfigDict(extra="forbid")

    #: Only required to be non-empty. The password *policy* deliberately does not
    #: apply here: this is a credential to verify, not a value to accept, and
    #: rejecting a short guess with a 422 would distinguish "malformed" from
    #: "wrong" - telling an attacker their guess was at least well-formed. Every
    #: incorrect current password should look identical.
    current_password: SecretStr = Field(min_length=1)
    #: The policy applies here, where a new value is actually being set.
    new_password: PlainPassword


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


class UserListPagination(BaseModel):
    """Page metadata for a user listing."""

    model_config = ConfigDict(extra="forbid")

    page: int
    page_size: int
    total: int
    total_pages: int


class UserListResponse(BaseModel):
    """One page of the caller's own tenant's users."""

    model_config = ConfigDict(extra="forbid")

    items: list[UserDetailResponse]
    pagination: UserListPagination


class PasswordChangeResponse(BaseModel):
    """Outcome of a password change."""

    model_config = ConfigDict(extra="forbid")

    success: bool = True
    #: How many refresh sessions the change ended. Every existing session is
    #: revoked, so other devices must sign in again with the new password.
    sessions_revoked: int


class UserAuditEntryResponse(BaseModel):
    """One lifecycle audit row.

    ``metadata`` carries only identifiers and before/after values written by
    :mod:`app.services.users.service` - never a password, hash, token or nonce.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    action: str
    actor_user_id: uuid.UUID | None
    created_at: datetime
    metadata: dict[str, Any] | None = Field(default=None)


class UserAuditResponse(BaseModel):
    """A page of one user's lifecycle audit history."""

    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    items: list[UserAuditEntryResponse]
    pagination: UserListPagination
