"""Add tour videos without changing existing catalogue or administrator data."""

import sqlalchemy as sa

from alembic import op

revision = '20261109_0028'
down_revision = '20261107_0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tour_videos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'tour_id', sa.Integer(), sa.ForeignKey('tours.id', ondelete='CASCADE'), nullable=False
        ),
        sa.Column('video_url', sa.String(500), nullable=False),
        sa.Column('poster_url', sa.String(500), nullable=True),
        sa.Column('order', sa.Integer(), server_default='0', nullable=False),
        sa.CheckConstraint('"order" >= 0', name='ck_tour_video_order'),
    )
    op.create_index('ix_tour_videos_tour_id', 'tour_videos', ['tour_id'])


def downgrade():
    op.drop_index('ix_tour_videos_tour_id', table_name='tour_videos')
    op.drop_table('tour_videos')
