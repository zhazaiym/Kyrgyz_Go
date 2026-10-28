"""empty message

Revision ID: c262097a705d
Revises: 20261026_0008
Create Date: 2026-10-27 16:05:16.924909

"""

revision = 'c262097a705d'
down_revision = '20261026_0008'
branch_labels = None
depends_on = None


def upgrade():
    # Keep travel selections: the application still uses this table.
    pass


def downgrade():
    pass
