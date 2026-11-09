"""Remove administrator MFA: TOTP secrets, recovery codes and trusted browsers."""

import sqlalchemy as sa

from alembic import op

revision = '20261108_0029'
down_revision = '20261107_0028'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index('ix_admin_trusted_devices_admin_id', table_name='admin_trusted_devices')
    op.drop_table('admin_trusted_devices')
    op.drop_column('admins', 'recovery_code_hashes')
    op.drop_column('admins', 'totp_last_used_step')
    op.drop_column('admins', 'totp_secret_encrypted')


def downgrade():
    op.add_column(
        'admins', sa.Column('totp_secret_encrypted', sa.String(length=255), nullable=True)
    )
    op.add_column('admins', sa.Column('totp_last_used_step', sa.Integer(), nullable=True))
    op.add_column(
        'admins', sa.Column('recovery_code_hashes', sa.JSON(), server_default='[]', nullable=False)
    )
    op.create_table(
        'admin_trusted_devices',
        sa.Column('id', sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            'admin_id', sa.Integer(), sa.ForeignKey('admins.id', ondelete='CASCADE'), nullable=False
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('token_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('label', sa.String(200), nullable=False),
    )
    op.create_index('ix_admin_trusted_devices_admin_id', 'admin_trusted_devices', ['admin_id'])
