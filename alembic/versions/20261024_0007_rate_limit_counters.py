"""Add persistent counters for request rate limits."""

from alembic import op
import sqlalchemy as sa


revision = "20261024_0007"
down_revision = "20261024_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key_hash"),
    )
    op.create_index(
        "ix_rate_limit_counters_window_start",
        "rate_limit_counters",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_counters_window_start",
        table_name="rate_limit_counters",
    )
    op.drop_table("rate_limit_counters")
