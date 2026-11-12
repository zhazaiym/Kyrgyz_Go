from uuid import uuid4

import pytest

PASSWORD = 'SimplePassword123!'


def unique_login():
    return 'user_' + uuid4().hex[:12]


@pytest.mark.parametrize('route', ['/auth', '/account'])
def test_registration_needs_only_login_and_password(client, route):
    login = unique_login()
    registered = client.post(f'{route}/register', json={'username': login, 'password': PASSWORD})
    assert registered.status_code == 201, registered.text
    assert registered.json()['username'] == login
    assert registered.json()['email'] is None

    signed_in = client.post(f'{route}/login', json={'username': login, 'password': PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()['client_id'] == registered.json()['client_id']
    headers = {'Authorization': 'Bearer ' + signed_in.json()['access_token']}
    assert client.get(f'{route}/me', headers=headers).json()['username'] == login


def test_registration_ignores_phone_and_email_fields(client):
    login = unique_login()
    response = client.post(
        '/account/register',
        json={
            'username': login,
            'password': PASSWORD,
            'phone': '+996700000000',
            'email': login + '@example.com',
        },
    )
    assert response.status_code == 201
    assert response.json()['email'] is None
    assert response.json()['phone'] is None


@pytest.mark.parametrize(
    'body',
    [
        {'username': 'ab', 'password': PASSWORD},
        {'username': 'has space', 'password': PASSWORD},
        {'username': 'valid_login', 'password': 'short'},
        {'password': PASSWORD},
        {'username': 'valid_login'},
    ],
)
def test_registration_rejects_bad_login_or_password(client, body):
    assert client.post('/account/register', json=body).status_code == 422


def test_duplicate_login_is_rejected(client):
    login = unique_login()
    body = {'username': login, 'password': PASSWORD}
    assert client.post('/auth/register', json=body).status_code == 201
    assert client.post('/account/register', json=body).status_code == 409


def test_wrong_password_is_rejected(client):
    login = unique_login()
    client.post('/account/register', json={'username': login, 'password': PASSWORD})
    response = client.post('/account/login', json={'username': login, 'password': 'Wrong12345!'})
    assert response.status_code == 401
    assert response.json()['detail']['message'] == 'Неверный логин или пароль'
