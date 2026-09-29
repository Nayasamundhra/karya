"""static qr token, retire kiosk tables, per-tenant max shift hours

Switches presence's QR signal from a rotating, single-use challenge to one
static, never-expiring token per attendance location
(`attendance_locations.qr_token`) - a tenant now prints/displays one QR
permanently instead of running a kiosk screen that re-fetches a code every
few seconds. See `backend/README.md`'s presence section for the trade-off
this accepts (GPS becomes the only signal that actually gates a check-in;
the QR just identifies which location a scan is against).

`gen_random_uuid()` is volatile, so PostgreSQL evaluates it once per
*existing* row when the column is added (not once for the whole
statement) - every already-configured location gets its own distinct
token, not a shared one.

With no rotation left, the tables that only ever existed to support it -
`qr_challenges` (the old challenge) and `display_tokens` (the kiosk
credential that kept re-requesting one) - are dropped outright rather than
left dormant.

Also adds `attendance_locations.max_shift_hours` - the forgotten-checkout
auto-close cutoff, moved from a global setting to a per-location one (same
"site-specific tuning knob" pattern as `geofence_radius_meters`), since a
9-to-5 office and 24h on-call staff need genuinely different numbers.

Revision ID: 366b2027c168
Revises: 06115be25b5a
Create Date: 2026-09-21 07:02:06.156580+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '366b2027c168'
down_revision: str | None = '06115be25b5a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'attendance_locations',
        sa.Column(
            'qr_token',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f('uq_attendance_locations_qr_token'),
        'attendance_locations',
        ['qr_token'],
    )
    op.add_column(
        'attendance_locations',
        sa.Column(
            'max_shift_hours',
            sa.Integer(),
            server_default=sa.text('16'),
            nullable=False,
        ),
    )

    # Dropped in reverse dependency order so foreign keys never block a drop.
    op.drop_index('ix_display_tokens_tenant_id', table_name='display_tokens')
    op.drop_index('ix_display_tokens_location_id', table_name='display_tokens')
    op.drop_table('display_tokens')

    op.drop_index('ix_qr_challenges_tenant_id', table_name='qr_challenges')
    op.drop_index(op.f('ix_qr_challenges_location_id'), table_name='qr_challenges')
    op.drop_index('ix_qr_challenges_expires_at', table_name='qr_challenges')
    op.drop_table('qr_challenges')


def downgrade() -> None:
    op.create_table(
        'qr_challenges',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('nonce', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['location_id'], ['attendance_locations.id'], name=op.f('fk_qr_challenges_location_id_attendance_locations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_qr_challenges_tenant_id_tenants'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_qr_challenges')),
        sa.UniqueConstraint('nonce', name=op.f('uq_qr_challenges_nonce')),
    )
    op.create_index('ix_qr_challenges_expires_at', 'qr_challenges', ['expires_at'], unique=False)
    op.create_index(op.f('ix_qr_challenges_location_id'), 'qr_challenges', ['location_id'], unique=False)
    op.create_index('ix_qr_challenges_tenant_id', 'qr_challenges', ['tenant_id'], unique=False)

    op.create_table(
        'display_tokens',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=True),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name=op.f('fk_display_tokens_created_by_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['location_id'], ['attendance_locations.id'], name=op.f('fk_display_tokens_location_id_attendance_locations'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_display_tokens_tenant_id_tenants'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_display_tokens')),
        sa.UniqueConstraint('token_hash', name=op.f('uq_display_tokens_token_hash')),
    )
    op.create_index('ix_display_tokens_location_id', 'display_tokens', ['location_id'], unique=False)
    op.create_index('ix_display_tokens_tenant_id', 'display_tokens', ['tenant_id'], unique=False)

    op.drop_column('attendance_locations', 'max_shift_hours')
    op.drop_constraint(
        op.f('uq_attendance_locations_qr_token'), 'attendance_locations', type_='unique'
    )
    op.drop_column('attendance_locations', 'qr_token')
