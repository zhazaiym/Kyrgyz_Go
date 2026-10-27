"""A chat session belongs to at most one travel selection."""

import sqlalchemy as sa

from alembic import op

revision = '20261028_0012'
down_revision = '20261027_0011'
branch_labels = None
depends_on = None


def upgrade():
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                'SELECT session_id FROM travel_selections WHERE session_id IS NOT NULL '
                'GROUP BY session_id HAVING count(*) > 1 LIMIT 1'
            )
        )
        .first()
    )
    if duplicate:
        raise RuntimeError(
            'Duplicate travel_selections.session_id: resolve the conflicting selections '
            'before upgrading; no selections have been deleted.'
        )
    op.create_unique_constraint(
        'uq_travel_selections_session_id', 'travel_selections', ['session_id']
    )


def downgrade():
    op.drop_constraint('uq_travel_selections_session_id', 'travel_selections', type_='unique')
