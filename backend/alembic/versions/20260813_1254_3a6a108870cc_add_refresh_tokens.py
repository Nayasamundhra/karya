"""add refresh_tokens

Adds the Phase 2 authentication-state table. Only a SHA-256 digest of each
refresh token is stored (`token_hash`), never the raw value.

Both foreign keys are ON DELETE CASCADE: refresh tokens are sessions, not
records worth keeping, so they should disappear with their user or tenant. This
is deliberately different from the Phase 1 attendance/audit tables, whose
RESTRICT / SET NULL rules are left untouched.

`ix_refresh_tokens_user_id_active` is a partial index (WHERE revoked_at IS NULL)
so active-session lookups stay cheap no matter how many revoked rows accumulate.

Revision ID: 3a6a108870cc
Revises: 61371755bbc6
Create Date: 2026-08-13 12:54:15.900018+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3a6a108870cc'
down_revision: str | None = '61371755bbc6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('refresh_tokens',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_refresh_tokens_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'], unique=False)
    op.create_index('ix_refresh_tokens_tenant_id', 'refresh_tokens', ['tenant_id'], unique=False)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_user_id_active', 'refresh_tokens', ['user_id'], unique=False, postgresql_where=sa.text('revoked_at IS NULL'))


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_user_id_active', table_name='refresh_tokens', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_tenant_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_expires_at', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
