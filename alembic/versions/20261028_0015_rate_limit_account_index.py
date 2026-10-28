"""Index rate-limit counters by scope/account for full password-reset cleanup."""

import sqlalchemy as sa
from alembic import op

revision = '20261028_0015'
down_revision = '20261028_0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('rate_limit_counters', sa.Column('scope', sa.String(64), nullable=True))
    op.add_column('rate_limit_counters', sa.Column('account_id', sa.String(128), nullable=True))
    # Old rows contain only a one-way hash, so their account dimension cannot be recovered.
    # These are short-lived counters; clearing them once lets the next request repopulate metadata.
    op.execute(sa.text('DELETE FROM rate_limit_counters'))
    op.alter_column('rate_limit_counters', 'scope', nullable=False)
    op.create_index(
        'ix_rate_limit_counters_scope_account', 'rate_limit_counters', ['scope', 'account_id']
    )


def downgrade():
    op.drop_index('ix_rate_limit_counters_scope_account', table_name='rate_limit_counters')
    op.drop_column('rate_limit_counters', 'account_id')
    op.drop_column('rate_limit_counters', 'scope')
