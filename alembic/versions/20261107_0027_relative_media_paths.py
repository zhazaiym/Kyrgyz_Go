"""Remove deployment hosts from locally stored media references."""

import sqlalchemy as sa

from alembic import op

revision = '20261107_0027'
down_revision = '20261107_0026'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    quote = connection.dialect.identifier_preparer.quote
    for table in inspector.get_table_names():
        for column in inspector.get_columns(table):
            if column['name'] in {'image', 'main_image', 'qr_code'}:
                name = quote(column['name'])
                # External catalogue images keep their original source. Only
                # paths served from our media volume lose their deployment host.
                connection.execute(
                    sa.text(
                        f"UPDATE {quote(table)} SET {name} = regexp_replace({name}, '^https?://[^/]+', '') "
                        f"WHERE {name} ~ '^https?://[^/]+/media/'"
                    )
                )


def downgrade():
    # The previous deployment host cannot be reconstructed safely.
    pass
