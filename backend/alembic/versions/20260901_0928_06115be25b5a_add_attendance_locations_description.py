"""add attendance_locations description

An optional free-text address/description for a tenant's attendance
location (PRD §7's "optional description/address"). Nullable, no backfill
needed - every existing location simply has none until an admin sets one.
Purely a human-facing label: presence verification never reads it.

Revision ID: 06115be25b5a
Revises: c19280cd25f1
Create Date: 2026-09-01 09:28:53.764869+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '06115be25b5a'
down_revision: str | None = 'c19280cd25f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('attendance_locations', sa.Column('description', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('attendance_locations', 'description')
