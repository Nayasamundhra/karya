"""attendance_events.event_timestamp defaults to clock_timestamp(), not now()

Revision ID: 127b35de9c9f
Revises: 823cf77034dc
Create Date: 2026-08-17 17:11:51.659178+00:00

WHY THIS MIGRATION EXISTS
=========================

Phase 7 found that `event_timestamp DEFAULT now()` can record a CHECK_OUT with an
*earlier* timestamp than the CHECK_IN it followed, which permanently corrupts the
derived attendance state. `now()` is the **transaction start** time, not the
moment of insertion:

  1. Transaction B begins.
  2. Transaction A begins later, takes the user row lock, and inserts a CHECK_IN
     stamped at A's start time.
  3. B has been blocked on that lock the whole time. A commits; B wakes, correctly
     observes the CHECK_IN, and inserts a legitimate CHECK_OUT - stamped at *B's*
     start time, which is earlier than A's.
  4. `ORDER BY event_timestamp DESC` now reports CHECK_IN as the latest event, so
     the user is derived as CHECKED_IN despite having checked out. They show as
     present on the team dashboard, and the day's sessions mis-pair.

Reproduced against PostgreSQL 18.4 before this change: two events stored in the
order `[CHECK_OUT, CHECK_IN]` with a 0.536 s inversion, and
`get_current_state` returning CHECKED_IN.

The Phase 4 row lock serialises the *decision* correctly; it cannot serialise a
timestamp that was already fixed when the transaction began. `clock_timestamp()`
reads the wall clock at insertion, so stored order always matches commit order.

It also makes the value distinct per statement. `now()` is constant within a
transaction, so two events written in one transaction shared a timestamp and the
"latest event" query had to break the tie arbitrarily - which it did differently
depending on whether the planner chose a sequential or an index scan.

This changes no column type, nullability, index or constraint, and no application
code sets the column - the service omits it so the default applies. Existing rows
are untouched: their timestamps stay exactly as recorded.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "127b35de9c9f"
down_revision: str | None = "823cf77034dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "attendance_events",
        "event_timestamp",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("clock_timestamp()"),
    )


def downgrade() -> None:
    # Restores the Phase 1 default. Reversible, but note that reverting
    # reintroduces the inversion described above.
    op.alter_column(
        "attendance_events",
        "event_timestamp",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("now()"),
    )
