"""Add optimistic concurrency version to chat sessions."""

import sqlalchemy as sa

from alembic import op

revision = '20261024_0006'
down_revision = '20261024_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'chat_sessions',
        sa.Column('message_version', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('chat_sessions', 'message_version')
