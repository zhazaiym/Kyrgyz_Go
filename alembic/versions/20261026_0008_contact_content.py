"""Contact links and automatic content ordering."""

import sqlalchemy as sa

from alembic import op

revision = '20261026_0008'
down_revision = '20261024_0007'
branch_labels = None
depends_on = None


def upgrade():
    # WhatsApp шилтемесинин узундугун көбөйтүү.
    with op.batch_alter_table('contacts') as batch:
        batch.alter_column(
            'whatsapp', existing_type=sa.String(50), type_=sa.String(500), existing_nullable=True
        )

    # Мурун кошулган жазуулардын иретин ID боюнча коюу.
    for table_name in ('about_sections', 'faqs'):
        table = sa.table(table_name, sa.column('id', sa.Integer), sa.column('order', sa.Integer))

        op.execute(table.update().values(order=table.c.id))


def downgrade():
    # Маалымат жоголбошу үчүн узун шилтемелерди
    # жана коюлган иретти сактайбыз.
    pass
