"""Merge the email-auth and password-reset migration branches."""

revision = "20261024_0005"
down_revision = ("45920e53cfc4", "20261023_0004")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
