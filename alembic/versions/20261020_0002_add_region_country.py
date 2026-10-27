"""add optional country relation to regions

Revision ID: 20261020_0002
Revises: 15eb0352f12a
Create Date: 2026-10-20
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '20261020_0002'
down_revision: Union[str, Sequence[str], None] = '15eb0352f12a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('regions') as batch_op:
        batch_op.add_column(sa.Column('country_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_regions_country_id_countries', 'countries', ['country_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('regions') as batch_op:
        batch_op.drop_constraint('fk_regions_country_id_countries', type_='foreignkey')
        batch_op.drop_column('country_id')
