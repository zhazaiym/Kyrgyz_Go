
"""add travel selections

Revision ID: 49b7dccc2836
Revises: 20261021_0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "49b7dccc2836"
down_revision: Union[str, Sequence[str], None] = "20261021_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "travel_selections",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True
        ),

        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("chat_clients.id"),
            nullable=False
        ),

        sa.Column(
            "tour_id",
            sa.Integer(),
            sa.ForeignKey("tours.id"),
            nullable=True
        ),

        sa.Column(
            "hotel_id",
            sa.Integer(),
            sa.ForeignKey("hotels.id"),
            nullable=True
        ),

        sa.Column(
            "transport_id",
            sa.Integer(),
            sa.ForeignKey("transports.id"),
            nullable=True
        ),

        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("chat_sessions.id"),
            nullable=True
        ),

        sa.Column(
            "status",
            sa.String(30),
            nullable=False
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),
    )

    op.create_index(
        "ix_travel_selections_client_id",
        "travel_selections",
        ["client_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_travel_selections_client_id",
        table_name="travel_selections"
    )

    op.drop_table("travel_selections")
