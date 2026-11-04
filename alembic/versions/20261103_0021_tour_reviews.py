"""Add public tour reviews."""

import sqlalchemy as sa

from alembic import op

revision = '20261103_0021'
down_revision = '20261030_0020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tour_reviews',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tour_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_tour_reviews_rating_range'),
        sa.ForeignKeyConstraint(['client_id'], ['chat_clients.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tour_id'], ['tours.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tour_id', 'client_id', name='uq_tour_reviews_tour_client'),
    )
    op.create_index('ix_tour_reviews_tour_id', 'tour_reviews', ['tour_id'], unique=False)
    op.create_index('ix_tour_reviews_client_id', 'tour_reviews', ['client_id'], unique=False)


def downgrade():
    op.drop_index('ix_tour_reviews_client_id', table_name='tour_reviews')
    op.drop_index('ix_tour_reviews_tour_id', table_name='tour_reviews')
    op.drop_table('tour_reviews')
