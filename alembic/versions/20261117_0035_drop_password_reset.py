"""Drop password reset tokens: sign-in is by login and password or a social network only.

Revision ID: 20261117_0035
Revises: 20261112_0034
"""

import sqlalchemy as sa

from alembic import op

revision = '20261117_0035'
down_revision = '20261112_0034'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('password_reset_tokens')


def downgrade():
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('chat_clients.id'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_password_reset_tokens_client_id', 'password_reset_tokens', ['client_id'])
    op.create_index(
        'ix_password_reset_tokens_token_hash', 'password_reset_tokens', ['token_hash'], unique=True
    )
    op.create_index('ix_password_reset_tokens_expires_at', 'password_reset_tokens', ['expires_at'])
