"""Reviews wait for a manager before they are shown and counted in the rating.

Existing reviews start as pending too: nobody has checked them yet.

Revision ID: 20261117_0037
Revises: 20261117_0036
"""

import sqlalchemy as sa

from alembic import op

revision = '20261117_0037'
down_revision = '20261117_0036'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'tour_reviews',
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
    )
    op.create_check_constraint(
        'ck_tour_reviews_status', 'tour_reviews', "status IN ('pending', 'published', 'rejected')"
    )
    op.create_index('ix_tour_reviews_status', 'tour_reviews', ['status'])


def downgrade():
    op.drop_index('ix_tour_reviews_status', table_name='tour_reviews')
    op.drop_constraint('ck_tour_reviews_status', 'tour_reviews', type_='check')
    op.drop_column('tour_reviews', 'status')
