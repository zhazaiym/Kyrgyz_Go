from datetime import datetime, timezone
from uuid import uuid4

from mysite.database.chat_models import ChatClient, ChatLoginToken
from mysite.database.db import SessionLocal
from mysite.database.token_utils import digest


def test_account_and_auth_login_share_client_and_seven_day_token(client):
    email = uuid4().hex + '@example.com'
    password = 'StrongSharedLoginPassword123!'
    registered = client.post(
        '/account/register',
        json={
            'name': 'Shared Login',
            'phone': '+996700654321',
            'email': email,
            'password': password,
        },
    )
    assert registered.status_code == 201, registered.text

    login = client.post('/auth/login', json={'email': email, 'password': password})
    assert login.status_code == 200, login.text
    assert login.json()['client_id'] == registered.json()['client_id']
    assert 'refresh_token' not in login.json()

    with SessionLocal() as db:
        token = (
            db.query(ChatLoginToken)
            .filter(ChatLoginToken.token_hash == digest(login.json()['access_token']))
            .one()
        )
        client_row = db.get(ChatClient, registered.json()['client_id'])
        assert client_row is not None
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        assert 6.99 < (expires_at - datetime.now(timezone.utc)).total_seconds() / 86400 < 7.01

    account_login = client.post('/account/login', json={'email': email, 'password': password})
    assert account_login.status_code == 200, account_login.text
    assert account_login.json()['client_id'] == registered.json()['client_id']
    assert account_login.json()['name'] == 'Shared Login'
    assert account_login.json()['phone'] == '+996700654321'
    assert 'refresh_token' not in account_login.json()
