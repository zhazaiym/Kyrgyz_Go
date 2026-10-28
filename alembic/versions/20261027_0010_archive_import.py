"""Keep imported legacy records outside the application's public schema."""

import sqlalchemy as sa

from alembic import op

revision = '20261027_0010'
down_revision = '20261027_0009'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    names = set(sa.inspect(connection).get_table_names())
    legacy = names & {'chats', 'legacy_chat_messages', 'sqlite_merge_history'}
    if legacy:
        op.execute('CREATE SCHEMA IF NOT EXISTS archive')
        for name in sorted(legacy):
            op.execute(f'ALTER TABLE public."{name}" SET SCHEMA archive')
        if 'sqlite_merge_history' in legacy:
            op.execute('ALTER TABLE archive.sqlite_merge_history RENAME TO import_history')
    indexes = {item['name'] for item in sa.inspect(connection).get_indexes('tours')}
    if 'ix_tours_country_id' not in indexes:
        op.create_index('ix_tours_country_id', 'tours', ['country_id'])


def downgrade():
    # Archive preservation is intentional; a schema rollback must not lose it.
    pass
