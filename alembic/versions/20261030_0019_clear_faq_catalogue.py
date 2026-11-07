"""Clear FAQ entries from the public catalogue."""

import sqlalchemy as sa

from alembic import op

revision = '20261030_0019'
down_revision = '20261030_0018'
branch_labels = None
depends_on = None


def upgrade():
    # 0018 populated sample FAQs; the public FAQ page should stay empty.
    op.execute(sa.text('DELETE FROM faqs'))


def downgrade():
    # Deleted FAQ records are intentionally not recreated.
    pass
