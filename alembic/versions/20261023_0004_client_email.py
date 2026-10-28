"""Optional unique email for shared client authentication."""

import sqlalchemy as sa

from alembic import op

revision = '20261023_0004'
down_revision = '20261021_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_clients', sa.Column('email', sa.String(254), nullable=True))
    op.create_index('ix_chat_clients_email', 'chat_clients', ['email'], unique=True)


def downgrade():
    op.drop_index('ix_chat_clients_email', table_name='chat_clients')
    with op.batch_alter_table('chat_clients') as batch:
        batch.drop_column('email')
