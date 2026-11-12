"""More social sign-in services: encrypted client secrets, redirect sign-in state and login codes."""

import sqlalchemy as sa

from alembic import op

revision = '20261112_0033'
down_revision = '20261111_0032'
branch_labels = None
depends_on = None

PROVIDERS = (
    ('vk', 'VK ID'),
    ('telegram', 'Telegram'),
    ('yandex', 'Яндекс ID'),
    ('x', 'X (Twitter)'),
    ('github', 'GitHub'),
    ('discord', 'Discord'),
    ('microsoft', 'Microsoft'),
    ('tiktok', 'TikTok'),
)


def upgrade():
    op.add_column('auth_providers', sa.Column('client_secret', sa.Text()))
    providers = sa.table(
        'auth_providers',
        sa.column('provider', sa.String),
        sa.column('title', sa.String),
        sa.column('is_active', sa.Boolean),
    )
    op.bulk_insert(
        providers,
        [{'provider': key, 'title': title, 'is_active': False} for key, title in PROVIDERS],
    )
    op.create_table(
        'oauth_states',
        sa.Column('state_hash', sa.String(64), primary_key=True),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('code_verifier', sa.String(128)),
        sa.Column('return_to', sa.String(2048), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'social_login_codes',
        sa.Column('code_hash', sa.String(64), primary_key=True),
        sa.Column(
            'client_id',
            sa.Integer(),
            sa.ForeignKey('chat_clients.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table('social_login_codes')
    op.drop_table('oauth_states')
    op.execute(
        sa.text('DELETE FROM auth_providers WHERE provider IN :keys').bindparams(
            sa.bindparam('keys', [key for key, _ in PROVIDERS], expanding=True)
        )
    )
    op.drop_column('auth_providers', 'client_secret')
