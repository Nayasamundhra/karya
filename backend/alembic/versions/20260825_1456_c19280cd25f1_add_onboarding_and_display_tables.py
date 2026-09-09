"""add onboarding and display tables

Two independent additions:

`email_verification_tokens` proves a self-service onboarding admin controls
the email they signed up with, before their account is usable. Same shape as
`refresh_tokens`: only a SHA-256 digest of the token is stored, and both
foreign keys are ON DELETE CASCADE - this is authentication-adjacent
ephemeral state, not a record worth keeping once its user or tenant is gone.

`display_tokens` is a credential for one physical office-display kiosk. This
one is *not* session-shaped: both `tenant_id` and `location_id` are ON
DELETE RESTRICT (matching `attendance_locations` - a tenant with a live
kiosk cannot be deleted by accident), while `created_by_user_id` alone is
SET NULL (matching `audit_logs.actor_user_id` - the record of which kiosk
exists must outlive whichever admin happened to set it up).

Revision ID: c19280cd25f1
Revises: 127b35de9c9f
Create Date: 2026-08-25 14:56:04.670072+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c19280cd25f1'
down_revision: str | None = '127b35de9c9f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('display_tokens',
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
    sa.UniqueConstraint('token_hash', name=op.f('uq_display_tokens_token_hash'))
    )
    op.create_index('ix_display_tokens_location_id', 'display_tokens', ['location_id'], unique=False)
    op.create_index('ix_display_tokens_tenant_id', 'display_tokens', ['tenant_id'], unique=False)
    op.create_table('email_verification_tokens',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_email_verification_tokens_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_verification_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_verification_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_email_verification_tokens_token_hash'))
    )
    op.create_index('ix_email_verification_tokens_expires_at', 'email_verification_tokens', ['expires_at'], unique=False)
    op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_email_verification_tokens_user_id', table_name='email_verification_tokens')
    op.drop_index('ix_email_verification_tokens_expires_at', table_name='email_verification_tokens')
    op.drop_table('email_verification_tokens')
    op.drop_index('ix_display_tokens_tenant_id', table_name='display_tokens')
    op.drop_index('ix_display_tokens_location_id', table_name='display_tokens')
    op.drop_table('display_tokens')
