"""Index every foreign key: lookups and deletes of the parent no longer scan the child table.

Revision ID: 20261117_0036
Revises: 20261117_0035
"""

from alembic import op

revision = '20261117_0036'
down_revision = '20261117_0035'
branch_labels = None
depends_on = None

FOREIGN_KEYS = (
    ('districts', 'region_id'),
    ('helicopter_images', 'helicopter_id'),
    ('hotel_images', 'hotel_id'),
    ('hotels', 'district_id'),
    ('hotels', 'region_id'),
    ('regions', 'country_id'),
    ('social_login_codes', 'client_id'),
    ('tour_images', 'tour_id'),
    ('tour_programs', 'tour_id'),
    ('tours', 'category_id'),
    ('transport_images', 'transport_id'),
    ('travel_selections', 'hotel_id'),
    ('travel_selections', 'tour_id'),
    ('travel_selections', 'transport_id'),
    ('trekking_images', 'trekking_id'),
    ('trekking_programs', 'trekking_id'),
)


def upgrade():
    for table, column in FOREIGN_KEYS:
        op.create_index(f'ix_{table}_{column}', table, [column], if_not_exists=True)


def downgrade():
    for table, column in FOREIGN_KEYS:
        op.drop_index(f'ix_{table}_{column}', table_name=table, if_exists=True)
