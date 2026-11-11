import time
import uuid
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mysite.api import social_auth
from mysite.api.admin import password_hash
from mysite.database.chat_models import ChatClient
from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.social_models import AuthProvider, ClientIdentity

GOOGLE_ID = '1234567890-kerbentest.apps.googleusercontent.com'
FACEBOOK_ID = '987654321012345'
SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ADMIN_PASSWORD = 'SocialAdminPassword123!'


def _configure(provider, app_id, active=True):
    with SessionLocal() as db:
        row = db.get(AuthProvider, provider)
        row.app_id = app_id
        row.is_active = active
        db.commit()


@pytest.fixture
def providers():
    _configure('google', GOOGLE_ID)
    _configure('facebook', FACEBOOK_ID)
    yield
    _configure('google', None, False)
    _configure('facebook', None, False)


@pytest.fixture
def google_keys(monkeypatch):
    monkeypatch.setattr(
        social_auth.google_keys,
        'get_signing_key_from_jwt',
        lambda token: SimpleNamespace(key=SIGNING_KEY.public_key()),
    )


def _google_token(**overrides):
    now = int(time.time())
    claims = {
        'iss': 'https://accounts.google.com',
        'aud': GOOGLE_ID,
        'sub': uuid.uuid4().hex,
        'email': f'traveller.{uuid.uuid4().hex[:8]}@gmail.com',
        'email_verified': True,
        'iat': now,
        'exp': now + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, SIGNING_KEY, algorithm='RS256')


def _facebook(monkeypatch, app_id=FACEBOOK_ID, subject='10001', email=None):
    def graph(path, access_token, fields=None):
        if path == 'app':
            return {'id': app_id}
        return {'id': subject, 'email': email}

    monkeypatch.setattr(social_auth, 'graph', graph)


def _me(client, response):
    assert response.status_code == 200, response.text
    token = response.json()['access_token']
    return client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).json()


def test_providers_are_hidden_until_the_owner_enables_them(client, providers):
    assert client.get('/auth/providers').json() == {
        'google': {'enabled': True, 'client_id': GOOGLE_ID},
        'facebook': {'enabled': True, 'app_id': FACEBOOK_ID},
    }
    _configure('facebook', FACEBOOK_ID, active=False)
    _configure('google', 'not-a-client-id', active=True)
    assert client.get('/auth/providers').json() == {
        'google': {'enabled': False, 'client_id': None},
        'facebook': {'enabled': False, 'app_id': None},
    }
    response = client.post('/auth/facebook', json={'access_token': 'x' * 40})
    assert response.status_code == 404


def test_google_sign_in_creates_one_client_per_google_account(client, providers, google_keys):
    subject = uuid.uuid4().hex
    email = f'new.{subject[:8]}@gmail.com'
    first = _me(
        client,
        client.post('/auth/google', json={'credential': _google_token(sub=subject, email=email)}),
    )
    again = _me(
        client,
        client.post('/auth/google', json={'credential': _google_token(sub=subject, email=email)}),
    )
    assert first['client_id'] == again['client_id']
    assert first['email'] == email
    assert first['username'].startswith('new')


def test_google_links_an_existing_account_by_verified_email(client, providers, google_keys):
    email = f'linked.{uuid.uuid4().hex[:8]}@gmail.com'
    registered = client.post(
        '/auth/register',
        json={
            'username': f'linked_{uuid.uuid4().hex[:8]}',
            'password': 'LinkedPassword123!',
            'email': email,
        },
    ).json()
    signed_in = _me(
        client, client.post('/auth/google', json={'credential': _google_token(email=email)})
    )
    assert signed_in['client_id'] == registered['client_id']

    unverified = _me(
        client,
        client.post(
            '/auth/google', json={'credential': _google_token(email=email, email_verified=False)}
        ),
    )
    assert unverified['client_id'] != registered['client_id']
    assert unverified['email'] is None


@pytest.mark.parametrize(
    'overrides',
    [
        {'aud': 'someone-else.apps.googleusercontent.com'},
        {'iss': 'https://evil.example'},
        {'exp': int(time.time()) - 60},
    ],
    ids=['audience', 'issuer', 'expired'],
)
def test_google_rejects_tokens_for_other_apps_or_expired(client, providers, google_keys, overrides):
    response = client.post('/auth/google', json={'credential': _google_token(**overrides)})
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'invalid_credentials'


def test_google_rejects_a_token_signed_by_another_key(client, providers, monkeypatch):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        social_auth.google_keys,
        'get_signing_key_from_jwt',
        lambda token: SimpleNamespace(key=other.public_key()),
    )
    response = client.post('/auth/google', json={'credential': _google_token()})
    assert response.status_code == 401


def test_facebook_sign_in_checks_the_app_and_never_merges_by_email(client, providers, monkeypatch):
    email = f'fb.{uuid.uuid4().hex[:8]}@example.com'
    existing = client.post(
        '/auth/register',
        json={
            'username': f'fb_{uuid.uuid4().hex[:8]}',
            'password': 'FacebookPassword123!',
            'email': email,
        },
    ).json()
    subject = str(uuid.uuid4().int)[:15]
    _facebook(monkeypatch, subject=subject, email=email)
    first = _me(client, client.post('/auth/facebook', json={'access_token': 'f' * 40}))
    again = _me(client, client.post('/auth/facebook', json={'access_token': 'f' * 40}))
    assert first['client_id'] == again['client_id'] != existing['client_id']
    assert first['email'] is None
    with SessionLocal() as db:
        identity = db.query(ClientIdentity).filter_by(provider='facebook', subject=subject).one()
        assert identity.client_id == first['client_id']

    _facebook(monkeypatch, app_id='111111111111')
    response = client.post('/auth/facebook', json={'access_token': 'f' * 40})
    assert response.status_code == 401


def test_provider_outage_is_reported_as_unavailable(client, providers, monkeypatch):
    def broken(path, access_token, fields=None):
        raise social_auth.SocialLoginError(503, 'service_unavailable')

    monkeypatch.setattr(social_auth, 'graph', broken)
    response = client.post('/auth/facebook', json={'access_token': 'f' * 40})
    assert response.status_code == 503


def test_social_clients_cannot_sign_in_with_a_guessed_password(client, providers, google_keys):
    email = f'nopass.{uuid.uuid4().hex[:8]}@gmail.com'
    _me(client, client.post('/auth/google', json={'credential': _google_token(email=email)}))
    response = client.post('/auth/login', json={'email': email, 'password': 'password123'})
    assert response.status_code == 401
    with SessionLocal() as db:
        assert db.query(ChatClient).filter_by(email=email).one().password_hash.startswith('$argon2')


def _owner_page(client, role, method, path, data=None):
    username = f'social-{role}'
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if admin is None:
            admin = Admin(username=username, hashed_password=password_hash.hash(ADMIN_PASSWORD))
            db.add(admin)
        admin.role = role
        admin.is_active = True
        db.commit()
    client.post('/admin/login', data={'username': username, 'password': ADMIN_PASSWORD})
    try:
        return client.request(method, path, data=data, follow_redirects=False)
    finally:
        client.get('/admin/logout')


def test_only_the_owner_edits_keys_and_bad_ids_are_rejected(client, providers):
    assert _owner_page(client, 'manager', 'GET', '/admin/auth-provider/list').status_code == 403
    page = _owner_page(client, 'owner', 'GET', '/admin/auth-provider/list')
    assert page.status_code == 200
    assert 'Google' in page.text and 'Facebook' in page.text

    rejected = _owner_page(
        client,
        'owner',
        'POST',
        '/admin/auth-provider/edit/google',
        {'app_id': 'GOCSPX-secret-value', 'is_active': 'y', 'save': 'Save'},
    )
    assert rejected.status_code == 400
    assert 'не похоже на ID приложения' in rejected.text
    saved = _owner_page(
        client,
        'owner',
        'POST',
        '/admin/auth-provider/edit/google',
        {'app_id': f' {GOOGLE_ID} ', 'is_active': 'y', 'save': 'Save'},
    )
    assert saved.status_code in (302, 303)
    with SessionLocal() as db:
        assert db.get(AuthProvider, 'google').app_id == GOOGLE_ID
