"""Admin sessions belong to the panel alone: refresh-token columns go.

Revision ID: 20261117_0038
Revises: 20261117_0037
"""

import sqlalchemy as sa

from alembic import op

revision = '20261117_0038'
down_revision = '20261117_0037'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('admin_sessions', 'rotated_at')
    op.drop_column('admin_sessions', 'previous_refresh_hash')
    op.drop_column('admin_sessions', 'refresh_hash')


def downgrade():
    op.add_column('admin_sessions', sa.Column('refresh_hash', sa.String(64)))
    op.execute("UPDATE admin_sessions SET refresh_hash = encode(sha256(id::text::bytea), 'hex')")
    op.alter_column('admin_sessions', 'refresh_hash', nullable=False)
    op.create_unique_constraint(
        'admin_sessions_refresh_hash_key', 'admin_sessions', ['refresh_hash']
    )
    op.add_column('admin_sessions', sa.Column('previous_refresh_hash', sa.String(64)))
    op.add_column('admin_sessions', sa.Column('rotated_at', sa.DateTime(timezone=True)))
