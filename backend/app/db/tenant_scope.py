"""Helpers for tenant-scoped queries.

Tenant isolation in Karya is enforced by *always* constraining a query with the
tenant id taken from the authenticated user. These helpers make that constraint
explicit and hard to forget, and give future phases one obvious place to build
tenant-aware reads.

The tenant id passed in must always originate from
``current_user.tenant_id`` - never from a path, query string, header or body.
"""

from __future__ import annotations

import uuid
from typing import Protocol, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session


class _TenantOwned(Protocol):
    """Structural type for a model carrying a ``tenant_id`` column."""

    tenant_id: uuid.UUID


ModelT = TypeVar("ModelT", bound=_TenantOwned)


def tenant_scoped_select(model: type[ModelT], tenant_id: uuid.UUID) -> Select[tuple[ModelT]]:
    """Return ``SELECT * FROM <model> WHERE tenant_id = :tenant_id``.

    Start every read of a tenant-owned table from here, then narrow further:

        stmt = tenant_scoped_select(User, current_user.tenant_id).where(
            User.status == UserStatus.ACTIVE
        )
    """
    return select(model).where(model.tenant_id == tenant_id)  # type: ignore[arg-type]


def get_tenant_owned(
    session: Session,
    model: type[ModelT],
    *,
    entity_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> ModelT | None:
    """Fetch one row by id, but only if it belongs to ``tenant_id``.

    Returns ``None`` for both "does not exist" and "belongs to another tenant",
    which is what lets a caller answer either case with an identical 404 and
    avoid confirming that a foreign id exists.
    """
    return session.scalar(
        tenant_scoped_select(model, tenant_id).where(model.id == entity_id)  # type: ignore[attr-defined]
    )
