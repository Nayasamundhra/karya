"""initial schema

Creates the six Karya entities together with their primary keys, foreign keys
(including the per-relationship ON DELETE rules), unique constraints and
indexes:

    tenants, users, attendance_locations, qr_challenges, attendance_events,
    audit_logs

All primary keys are UUID with a ``gen_random_uuid()`` server default (built
into PostgreSQL 13+, so no extension is required). All timestamp columns are
TIMESTAMPTZ defaulting to ``now()``.

Revision ID: 61371755bbc6
Revises:
Create Date: 2026-08-13 11:34:22.700443+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '61371755bbc6'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('tenants',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tenants')),
    sa.UniqueConstraint('slug', name=op.f('uq_tenants_slug'))
    )
    op.create_table('attendance_locations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('latitude', sa.Double(), nullable=False),
    sa.Column('longitude', sa.Double(), nullable=False),
    sa.Column('geofence_radius_meters', sa.Integer(), server_default=sa.text('150'), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_attendance_locations_tenant_id_tenants'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attendance_locations')),
    sa.UniqueConstraint('tenant_id', name=op.f('uq_attendance_locations_tenant_id'))
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('employee_code', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=True),
    sa.Column('role', sa.String(length=30), server_default=sa.text("'STAFF'"), nullable=False),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'ACTIVE'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_users_tenant_id_tenants'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('tenant_id', 'email', name=op.f('uq_users_tenant_id_email')),
    sa.UniqueConstraint('tenant_id', 'employee_code', name=op.f('uq_users_tenant_id_employee_code'))
    )
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)
    op.create_table('attendance_events',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=20), nullable=False),
    sa.Column('event_timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('latitude', sa.Double(), nullable=True),
    sa.Column('longitude', sa.Double(), nullable=True),
    sa.Column('gps_accuracy_meters', sa.Double(), nullable=True),
    sa.Column('verification_status', sa.String(length=30), nullable=False),
    sa.Column('verification_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_attendance_events_tenant_id_tenants'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_attendance_events_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attendance_events'))
    )
    op.create_index('ix_attendance_events_event_timestamp', 'attendance_events', ['event_timestamp'], unique=False)
    op.create_index('ix_attendance_events_tenant_id', 'attendance_events', ['tenant_id'], unique=False)
    op.create_index('ix_attendance_events_tenant_id_user_id_event_timestamp', 'attendance_events', ['tenant_id', 'user_id', 'event_timestamp'], unique=False)
    op.create_index('ix_attendance_events_user_id', 'attendance_events', ['user_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('target_type', sa.String(length=50), nullable=True),
    sa.Column('target_id', sa.UUID(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_logs_actor_user_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_audit_logs_tenant_id_tenants'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'], unique=False)
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_tenant_id', 'audit_logs', ['tenant_id'], unique=False)
    op.create_table('qr_challenges',
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
    sa.UniqueConstraint('nonce', name=op.f('uq_qr_challenges_nonce'))
    )
    op.create_index('ix_qr_challenges_expires_at', 'qr_challenges', ['expires_at'], unique=False)
    op.create_index(op.f('ix_qr_challenges_location_id'), 'qr_challenges', ['location_id'], unique=False)
    op.create_index('ix_qr_challenges_tenant_id', 'qr_challenges', ['tenant_id'], unique=False)


def downgrade() -> None:
    # Dropped in reverse dependency order so foreign keys never block a drop.
    op.drop_index('ix_qr_challenges_tenant_id', table_name='qr_challenges')
    op.drop_index(op.f('ix_qr_challenges_location_id'), table_name='qr_challenges')
    op.drop_index('ix_qr_challenges_expires_at', table_name='qr_challenges')
    op.drop_table('qr_challenges')
    op.drop_index('ix_audit_logs_tenant_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('ix_attendance_events_user_id', table_name='attendance_events')
    op.drop_index('ix_attendance_events_tenant_id_user_id_event_timestamp', table_name='attendance_events')
    op.drop_index('ix_attendance_events_tenant_id', table_name='attendance_events')
    op.drop_index('ix_attendance_events_event_timestamp', table_name='attendance_events')
    op.drop_table('attendance_events')
    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('attendance_locations')
    op.drop_table('tenants')
