"""Restore client ownership for requests created through chat."""

import sqlalchemy as sa

from alembic import op

revision = 'b1268424d4ef'
down_revision = '20261103_0022'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text("""
            UPDATE travel_requests AS request
            SET client_id = booking.client_id
            FROM chat_booking_links AS booking
            WHERE booking.request_id = request.id
              AND request.client_id IS NULL
        """)
    )


def downgrade():
    # Восстановленные связи сохраняем.
    pass
