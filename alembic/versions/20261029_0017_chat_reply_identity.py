"""Associate generated replies with the exact user turn for failure cleanup."""

import sqlalchemy as sa

from alembic import op

revision = '20261029_0017'
down_revision = '20261028_0016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('reply_to_message_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_chat_messages_reply_to_message_id',
        'chat_messages',
        'chat_messages',
        ['reply_to_message_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_unique_constraint(
        'uq_chat_messages_reply_to_message_id', 'chat_messages', ['reply_to_message_id']
    )


def downgrade():
    op.drop_constraint('uq_chat_messages_reply_to_message_id', 'chat_messages', type_='unique')
    op.drop_constraint('fk_chat_messages_reply_to_message_id', 'chat_messages', type_='foreignkey')
    op.drop_column('chat_messages', 'reply_to_message_id')
