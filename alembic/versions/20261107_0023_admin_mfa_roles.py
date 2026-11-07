"""Add administrator roles and MFA storage."""

import sqlalchemy as sa

from alembic import op

revision = '20261107_0023'
down_revision = '20261103_0022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'admins', sa.Column('role', sa.String(length=30), server_default='owner', nullable=False)
    )
    op.add_column(
        'admins', sa.Column('totp_secret_encrypted', sa.String(length=255), nullable=True)
    )
    op.add_column('admins', sa.Column('totp_last_used_step', sa.Integer(), nullable=True))
    op.add_column(
        'admins', sa.Column('recovery_code_hashes', sa.JSON(), server_default='[]', nullable=False)
    )
    op.create_check_constraint(
        'ck_admin_role', 'admins', "role IN ('owner', 'manager', 'catalog_editor')"
    )


def downgrade():
    op.drop_constraint('ck_admin_role', 'admins', type_='check')
    op.drop_column('admins', 'recovery_code_hashes')
    op.drop_column('admins', 'totp_last_used_step')
    op.drop_column('admins', 'totp_secret_encrypted')
    op.drop_column('admins', 'role')
