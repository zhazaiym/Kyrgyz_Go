"""Tour coordinates and stored translations for public catalogue sections."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_0003'
down_revision = '20261020_0002'
branch_labels = None
depends_on = None

TABLES = (
    'abouts', 'about_sections', 'tour_categories', 'countries', 'regions',
    'districts', 'hotels', 'transports', 'helicopter_tours', 'trekkings',
    'contacts', 'faqs', 'tour_programs', 'trekking_programs',
)


def upgrade():
    op.add_column('tours', sa.Column('latitude', sa.Numeric(10, 7), nullable=True))
    op.add_column('tours', sa.Column('longitude', sa.Numeric(10, 7), nullable=True))
    for table in TABLES:
        op.add_column(table, sa.Column('translations', sa.JSON(), nullable=True))


def downgrade():
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column('translations')
    with op.batch_alter_table('tours') as batch:
        batch.drop_column('longitude')
        batch.drop_column('latitude')
