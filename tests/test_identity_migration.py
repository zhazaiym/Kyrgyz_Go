import os
import subprocess
import sys

import pytest

from tests.postgres_support import temporary_database


@pytest.mark.parametrize(
    'case', ['profile_only', 'matching_email', 'duplicate_owners', 'different_emails']
)
def test_legacy_email_migration_preserves_identity_or_rejects_ambiguity(case):
    script = '''
import os
import sys
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

case = sys.argv[1]
config = Config('alembic.ini')
command.upgrade(config, '20261027_0010')
engine = create_engine(os.environ['DATABASE_URL'])
try:
    canonical = 'existing@example.com' if case == 'different_emails' else (
        'migrate@example.com' if case == 'matching_email' else None)
    with engine.begin() as connection:
        identity = connection.scalar(text("""INSERT INTO chat_clients
            (username, email, password_hash, created_at)
            VALUES ('migrate_owner', :email, 'preserved_hash', CURRENT_TIMESTAMP) RETURNING id"""),
            {'email': canonical})
        connection.execute(text("""INSERT INTO client_profiles
            (client_id, name, phone, email, created_at)
            VALUES (:id, 'Preserved profile', '+996700123456', ' MIGRATE@EXAMPLE.COM ', CURRENT_TIMESTAMP)"""),
            {'id': identity})
        if case == 'duplicate_owners':
            connection.execute(text("""INSERT INTO chat_clients
                (username, email, password_hash, created_at)
                VALUES ('second_owner', 'migrate@example.com', 'other_hash', CURRENT_TIMESTAMP)"""))
    conflict = case in ('duplicate_owners', 'different_emails')
    try:
        command.upgrade(config, 'head')
    except RuntimeError as exc:
        assert conflict and 'Conflicting legacy client emails' in str(exc)
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261027_0010'
            assert connection.scalar(text('SELECT email FROM client_profiles')) == ' MIGRATE@EXAMPLE.COM '
            assert connection.scalar(text('SELECT email FROM chat_clients WHERE id=:id'), {'id': identity}) == canonical
    else:
        assert not conflict
        with engine.connect() as connection:
            assert connection.execute(text('SELECT id, email, password_hash FROM chat_clients')).one() == (
                identity, 'migrate@example.com', 'preserved_hash')
            assert connection.execute(text('SELECT client_id, name, phone FROM client_profiles')).one() == (
                identity, 'Preserved profile', '+996700123456')
        assert 'email' not in {column['name'] for column in inspect(engine).get_columns('client_profiles')}
        command.check(config)
        command.downgrade(config, '20261027_0010')
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT email FROM client_profiles')) == 'migrate@example.com'
        command.upgrade(config, 'head')
finally:
    engine.dispose()
'''
    with temporary_database() as url:
        result = subprocess.run(
            [sys.executable, '-c', script, case],
            env={**os.environ, 'DATABASE_URL': url},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_translation_migration_is_self_contained_and_downgrade_hides_stale_values():
    script = '''
import hashlib
import json
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

config = Config('alembic.ini')
command.upgrade(config, '20261028_0014')
engine = create_engine(__import__('os').environ['DATABASE_URL'])
old_hash = hashlib.md5(b'Old source', usedforsecurity=False).hexdigest()
translations = {'en': {'title': 'Stale English', '_source_hashes': {'title': old_hash}, '_manual_fields': ['title']}}
with engine.begin() as connection:
    connection.execute(text("""INSERT INTO abouts
        (title, description, experience_years, travelers_count, branches_count,
         destinations_count, routes_count, is_active, translations)
        VALUES ('Old source', NULL, 6, 28000, 3, 20, 100, TRUE, CAST(:translations AS json))"""),
        {'translations': json.dumps(translations)})
    connection.execute(text("UPDATE abouts SET title='New source'"))
command.downgrade(config, '20261028_0013')
with engine.connect() as connection:
    stored = connection.scalar(text('SELECT translations FROM abouts'))
    assert 'title' not in stored['en']
    assert '_source_hashes' not in stored['en']
engine.dispose()
'''
    with temporary_database() as url:
        env = {key: value for key, value in os.environ.items() if not key.startswith('GEMINI_')}
        env['DATABASE_URL'] = url
        result = subprocess.run(
            [sys.executable, '-B', '-c', script], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr
