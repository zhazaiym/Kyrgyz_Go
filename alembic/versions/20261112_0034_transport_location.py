"""Store where each vehicle is based so tours can offer the nearest transport."""

import sqlalchemy as sa

from alembic import op

revision = '20261112_0034'
down_revision = '20261112_0033'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('transports', sa.Column('latitude', sa.Numeric(10, 7), nullable=True))
    op.add_column('transports', sa.Column('longitude', sa.Numeric(10, 7), nullable=True))


def downgrade():
    op.drop_column('transports', 'longitude')
    op.drop_column('transports', 'latitude')
