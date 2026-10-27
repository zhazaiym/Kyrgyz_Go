import os
import subprocess
import sys

import pytest

PASSWORD = 'EmailPassword123!'


def test_customer_can_login_by_email_and_username(client):
    response = client.post(
        '/auth/register',
        json={'username': 'email_customer', 'email': ' Guest@Example.COM ', 'password': PASSWORD},
    )
    assert response.status_code == 201
    assert response.json()['email'] == 'guest@example.com'
    identity = response.json()['client_id']
    for credentials in (
        {'email': ' GUEST@example.com ', 'password': PASSWORD},
        {'username': 'EMAIL_CUSTOMER', 'password': PASSWORD},
        {'username': 'guest@example.com', 'password': PASSWORD},
    ):
        login = client.post('/auth/login', json=credentials)
        assert login.status_code == 200, login.text
        assert login.json()['client_id'] == identity
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        assert client.get('/auth/me', headers=headers).json()['email'] == 'guest@example.com'
        assert client.post('/chat/session', headers=headers).status_code == 200


def test_duplicate_email_is_rejected_case_insensitively(client):
    first = client.post(
        '/auth/register',
        json={
            'username': 'email_unique_first',
            'email': 'unique@example.com',
            'password': PASSWORD,
        },
    )
    assert first.status_code == 201
    duplicate = client.post(
        '/chat/auth/register',
        json={
            'username': 'email_unique_second',
            'email': 'UNIQUE@example.com',
            'password': PASSWORD,
        },
    )
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    'email', ['not-email', 'a@', '@example.com', 'a b@example.com', '', 'a@example..com']
)
def test_invalid_registration_email_is_rejected(client, email):
    response = client.post(
        '/auth/register', json={'username': 'invalid_email', 'email': email, 'password': PASSWORD}
    )
    assert response.status_code == 422


def test_unknown_account_and_wrong_password_have_identical_errors(client):
    assert (
        client.post(
            '/auth/register',
            json={
                'username': 'email_bad_password',
                'email': 'known@example.com',
                'password': PASSWORD,
            },
        ).status_code
        == 201
    )
    responses = [
        client.post('/auth/login', json=credentials)
        for credentials in (
            {'email': 'known@example.com', 'password': 'WrongPassword123!'},
            {'email': 'missing@example.com', 'password': PASSWORD},
            {'username': 'missing_username', 'password': PASSWORD},
            {'email': 'known@example.com', 'password': 'x'},
        )
    ]
    assert all(response.status_code == 401 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    assert responses[0].json()['detail']['message'] == 'Неверный email или пароль'


def test_legacy_username_registration_remains_supported(client):
    credentials = {'username': 'legacy_without_email', 'password': PASSWORD}
    registered = client.post('/auth/register', json=credentials)
    assert registered.status_code == 201
    assert registered.json()['email'] is None
    assert client.post('/chat/auth/login', json=credentials).status_code == 200


@pytest.mark.parametrize('identifiers', [{}, {'email': 'a@example.com', 'username': 'someone'}])
def test_login_requires_exactly_one_identifier(client, identifiers):
    assert client.post('/auth/login', json={**identifiers, 'password': PASSWORD}).status_code == 422


def test_email_migration_preserves_existing_accounts():
    script = """
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
import os

config = Config('alembic.ini')
command.upgrade(config, '20261021_0003')
engine = create_engine(os.environ['DATABASE_URL'])
with engine.begin() as connection:
    connection.execute(text("INSERT INTO chat_clients (username, password_hash, created_at) VALUES ('legacy_migration', 'preserved_hash', CURRENT_TIMESTAMP)"))
command.upgrade(config, 'head')
with engine.begin() as connection:
    row = connection.execute(text('SELECT username, password_hash, email FROM chat_clients')).one()
    assert tuple(row) == ('legacy_migration', 'preserved_hash', None)
    connection.execute(text("INSERT INTO chat_clients (username, password_hash, created_at) VALUES ('second_legacy', 'another_hash', CURRENT_TIMESTAMP)"))
command.downgrade(config, '20261021_0003')
assert 'email' not in {column['name'] for column in inspect(engine).get_columns('chat_clients')}
command.upgrade(config, 'head')
with engine.connect() as connection:
    assert connection.execute(text('SELECT COUNT(*) FROM chat_clients')).scalar() == 2
engine.dispose()
"""
    from tests.postgres_support import temporary_database

    with temporary_database() as url:
        environment = {**os.environ, 'DATABASE_URL': url}
        result = subprocess.run(
            [sys.executable, '-c', script], env=environment, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr
