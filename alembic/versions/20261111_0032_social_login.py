"""Sign in with Google and Facebook: provider settings and linked client identities."""

import sqlalchemy as sa

from alembic import op

revision = '20261111_0032'
down_revision = '20261109_0031'
branch_labels = None
depends_on = None


def upgrade():
    providers = op.create_table(
        'auth_providers',
        sa.Column('provider', sa.String(20), primary_key=True),
        sa.Column('title', sa.String(50), nullable=False),
        sa.Column('app_id', sa.String(255)),
        sa.Column('is_active', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        providers,
        [
            {'provider': 'google', 'title': 'Google', 'is_active': False},
            {'provider': 'facebook', 'title': 'Facebook', 'is_active': False},
        ],
    )
    op.create_table(
        'client_identities',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'client_id',
            sa.Integer(),
            sa.ForeignKey('chat_clients.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('email', sa.String(254)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('provider', 'subject', name='uq_client_identities_provider_subject'),
    )
    op.create_index('ix_client_identities_client_id', 'client_identities', ['client_id'])


def downgrade():
    op.drop_index('ix_client_identities_client_id', table_name='client_identities')
    op.drop_table('client_identities')
    op.drop_table('auth_providers')
