"""Add an optional video link to tours."""

import sqlalchemy as sa

from alembic import op

revision = '20261109_0030'
down_revision = '20261108_0029'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tours', sa.Column('video_url', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('tours', 'video_url')
