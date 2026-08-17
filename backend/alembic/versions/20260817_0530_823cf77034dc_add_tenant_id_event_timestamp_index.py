"""add tenant_id event_timestamp index

Supports the Phase 5 tenant-wide day query behind GET /attendance/team/today,
which constrains tenant and a one-day timestamp range but no single user.

The existing (tenant_id, user_id, event_timestamp) index cannot serve that
shape: with user_id unconstrained in the middle, PostgreSQL falls back to
bitmap-ANDing the tenant_id and event_timestamp indexes. Measured on 76,800
seeded events (8 tenants x 40 users x 120 days), that read 9,600 index entries -
every event the tenant had ever recorded - to return the day's 80 rows, and the
cost grows without bound as history deepens. With this index the same query is a
single index scan reading only those 80 rows (13 buffers -> 6, 0.99ms -> 0.22ms).

The table gains a fifth index, which costs a little on write. Attendance writes
are inherently low volume (two events per employee per day) whereas the dashboard
is the most frequently polled read, so the trade is worth it.

Revision ID: 823cf77034dc
Revises: 3a6a108870cc
Create Date: 2026-08-17 05:30:20.683969+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '823cf77034dc'
down_revision: str | None = '3a6a108870cc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index('ix_attendance_events_tenant_id_event_timestamp', 'attendance_events', ['tenant_id', 'event_timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_attendance_events_tenant_id_event_timestamp', table_name='attendance_events')
