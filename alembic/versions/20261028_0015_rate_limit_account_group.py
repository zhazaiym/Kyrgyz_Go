"""Group login counters so a password reset can clear every device."""

import sqlalchemy as sa

from alembic import op

revision = '20261028_0015'
down_revision = '20261028_0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('rate_limit_counters', sa.Column('group_hash', sa.String(64), nullable=True))
    op.create_index('ix_rate_limit_counters_group_hash', 'rate_limit_counters', ['group_hash'])


def downgrade():
    op.drop_index('ix_rate_limit_counters_group_hash', table_name='rate_limit_counters')
    op.drop_column('rate_limit_counters', 'group_hash')
