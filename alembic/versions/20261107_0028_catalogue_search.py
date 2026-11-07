"""Fuzzy catalogue search for the chat: pg_trgm, unaccent and editable keywords."""

import sqlalchemy as sa

from alembic import op

revision = '20261107_0028'
down_revision = '20261107_0027'
branch_labels = None
depends_on = None

TABLES = ('tours', 'helicopter_tours', 'trekkings')


def upgrade():
    # Both extensions are trusted in PostgreSQL 13+: the database owner may create them.
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE EXTENSION IF NOT EXISTS unaccent')
    for table in TABLES:
        op.add_column(table, sa.Column('search_keywords', sa.Text(), nullable=True))


def downgrade():
    for table in TABLES:
        op.drop_column(table, 'search_keywords')
