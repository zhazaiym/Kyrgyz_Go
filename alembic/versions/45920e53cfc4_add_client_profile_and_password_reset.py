
"""add client profile and password reset

Revision ID: 45920e53cfc4
Revises: 49b7dccc2836
Create Date: 2026-10-23 11:05:44.432422
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = "45920e53cfc4"

down_revision: Union[str, Sequence[str], None] = (
    "49b7dccc2836"
)

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # CLIENT PROFILES

    op.create_table(
        "client_profiles",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False
        ),

        sa.Column(
            "client_id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False
        ),

        sa.Column(
            "phone",
            sa.String(length=25),
            nullable=False
        ),

        sa.Column(
            "email",
            sa.String(length=254),
            nullable=False
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),

        sa.ForeignKeyConstraint(
            ["client_id"],
            ["chat_clients.id"]
        )
    )

    op.create_index(
        "ix_client_profiles_client_id",
        "client_profiles",
        ["client_id"],
        unique=True
    )

    op.create_index(
        "ix_client_profiles_email",
        "client_profiles",
        ["email"],
        unique=True
    )

    # PASSWORD RESET TOKENS

    op.create_table(
        "password_reset_tokens",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False
        ),

        sa.Column(
            "client_id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),

        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),

        sa.ForeignKeyConstraint(
            ["client_id"],
            ["chat_clients.id"]
        )
    )

    op.create_index(
        "ix_password_reset_tokens_client_id",
        "password_reset_tokens",
        ["client_id"],
        unique=False
    )

    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True
    )


def downgrade() -> None:

    # PASSWORD RESET TOKENS

    op.drop_index(
        "ix_password_reset_tokens_token_hash",
        table_name="password_reset_tokens"
    )

    op.drop_index(
        "ix_password_reset_tokens_client_id",
        table_name="password_reset_tokens"
    )

    op.drop_table(
        "password_reset_tokens"
    )

    # CLIENT PROFILES

    op.drop_index(
        "ix_client_profiles_email",
        table_name="client_profiles"
    )

    op.drop_index(
        "ix_client_profiles_client_id",
        table_name="client_profiles"
    )

    op.drop_table(
        "client_profiles"
    )
