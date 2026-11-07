"""Add authenticated ownership and selection links to travel requests."""

import sqlalchemy as sa

from alembic import op

revision = '20261103_0022'
down_revision = '20261103_0021'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('travel_requests', sa.Column('client_id', sa.Integer(), nullable=True))
    op.add_column('travel_requests', sa.Column('selection_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_travel_requests_client_id_chat_clients',
        'travel_requests',
        'chat_clients',
        ['client_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_travel_requests_selection_id_travel_selections',
        'travel_requests',
        'travel_selections',
        ['selection_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index('ix_travel_requests_client_id', 'travel_requests', ['client_id'], unique=False)
    op.create_unique_constraint(
        'uq_travel_requests_selection_id', 'travel_requests', ['selection_id']
    )
    op.execute(
        sa.text(
            'UPDATE travel_requests AS request '
            'SET client_id = booking.client_id '
            'FROM chat_booking_links AS booking '
            'WHERE booking.request_id = request.id AND request.client_id IS NULL'
        )
    )


def downgrade():
    op.drop_constraint('uq_travel_requests_selection_id', 'travel_requests', type_='unique')
    op.drop_index('ix_travel_requests_client_id', table_name='travel_requests')
    op.drop_constraint(
        'fk_travel_requests_selection_id_travel_selections', 'travel_requests', type_='foreignkey'
    )
    op.drop_constraint(
        'fk_travel_requests_client_id_chat_clients', 'travel_requests', type_='foreignkey'
    )
    op.drop_column('travel_requests', 'selection_id')
    op.drop_column('travel_requests', 'client_id')
