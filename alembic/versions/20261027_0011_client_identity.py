"""Canonical client emails and durable selected-service booking snapshots."""

import sqlalchemy as sa

from alembic import op

revision = '20261027_0011'
down_revision = '20261027_0010'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    identities = """
        WITH identities AS (
            SELECT id AS client_id, lower(btrim(email)) AS email
            FROM chat_clients WHERE email IS NOT NULL
            UNION
            SELECT client_id, lower(btrim(email)) AS email FROM client_profiles
        )
    """
    # Never merge different account owners or silently choose between emails.
    conflicting_client = connection.execute(
        sa.text(
            identities
            + """
        SELECT client_id FROM identities
        GROUP BY client_id HAVING count(DISTINCT email) > 1 LIMIT 1
    """
        )
    ).first()
    conflicting_email = connection.execute(
        sa.text(
            identities
            + """
        SELECT min(client_id) FROM identities
        GROUP BY email HAVING count(DISTINCT client_id) > 1 OR email = '' LIMIT 1
    """
        )
    ).first()
    if conflicting_client or conflicting_email:
        raise RuntimeError(
            'Conflicting legacy client emails: resolve account ownership before migration'
        )
    op.execute('UPDATE chat_clients SET email = lower(btrim(email)) WHERE email IS NOT NULL')
    op.execute("""UPDATE chat_clients AS c SET email = lower(btrim(p.email))
                  FROM client_profiles AS p WHERE p.client_id = c.id AND c.email IS NULL""")
    op.create_index(
        'uq_chat_clients_email_lower', 'chat_clients', [sa.text('lower(email)')], unique=True
    )
    op.drop_index('ix_client_profiles_email', table_name='client_profiles')
    op.drop_column('client_profiles', 'email')
    op.add_column('travel_requests', sa.Column('selected_services', sa.JSON(), nullable=True))


def downgrade():
    # Restore the per-profile email column for older authentication code.
    op.add_column('client_profiles', sa.Column('email', sa.String(254), nullable=True))
    op.execute("""UPDATE client_profiles AS p SET email = c.email
                  FROM chat_clients AS c WHERE p.client_id = c.id""")
    op.alter_column('client_profiles', 'email', nullable=False)
    op.create_index('ix_client_profiles_email', 'client_profiles', ['email'], unique=True)
    op.drop_index('uq_chat_clients_email_lower', table_name='chat_clients')
    op.drop_column('travel_requests', 'selected_services')
