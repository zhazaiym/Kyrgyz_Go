"""Add revocable administrator sessions and trusted browsers."""

import sqlalchemy as sa

from alembic import op

revision = '20261107_0026'
down_revision = '20261107_0025'
branch_labels = None
depends_on = None


def upgrade():
    for name in ('admin_sessions', 'admin_trusted_devices'):
        common = [
            sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
            sa.Column(
                'admin_id',
                sa.Integer(),
                sa.ForeignKey('admins.id', ondelete='CASCADE'),
                nullable=False,
            ),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('revoked_at', sa.DateTime(timezone=True)),
        ]
        if name == 'admin_sessions':
            common.extend(
                [
                    sa.Column('refresh_hash', sa.String(64), unique=True, nullable=False),
                    sa.Column('previous_refresh_hash', sa.String(64)),
                    sa.Column('rotated_at', sa.DateTime(timezone=True)),
                    sa.Column('user_agent', sa.String(200), nullable=False),
                ]
            )
        else:
            common.extend(
                [
                    sa.Column('token_hash', sa.String(64), unique=True, nullable=False),
                    sa.Column('label', sa.String(200), nullable=False),
                ]
            )
        op.create_table(name, *common)
        op.create_index(f'ix_{name}_admin_id', name, ['admin_id'])


def downgrade():
    op.drop_table('admin_trusted_devices')
    op.drop_table('admin_sessions')
