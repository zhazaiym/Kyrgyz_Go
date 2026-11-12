import base64
import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from mysite.api import oauth_providers
from mysite.api.admin import password_hash
from mysite.api.provider_secrets import open_secret, seal_secret
from mysite.api.social_auth import configured
from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.social_models import AuthProvider, ClientIdentity

SITE = 'https://new-site.example'
RETURN_TO = f'{SITE}/auth/callback?next=%2Ftours'
SECRET = 'client-secret-value-123'
APP_IDS = {
    'vk': '51234567',
    'yandex': '0123456789abcdef0123456789abcdef',
    'x': 'Zm9vYmFyYmF6cXV4cXV1eA',
    'github': 'Ov23liAbCdEf12345678',
    'discord': '123456789012345678',
    'microsoft': '12345678-1234-1234-1234-123456789abc',
    'tiktok': 'awabcdef12345678',
}
PROFILES = {
    'vk': ('https://id.vk.ru/oauth2/user_info', {'user': {'user_id': 501}}),
    'yandex': ('https://login.yandex.ru/info', {'id': '502', 'client_id': APP_IDS['yandex']}),
    'x': ('https://api.x.com/2/users/me', {'data': {'id': '503'}}),
    'github': ('https://api.github.com/user', {'id': 504}),
    'discord': ('https://discord.com/api/users/@me', {'id': '505', 'verified': True}),
    'microsoft': ('https://graph.microsoft.com/v1.0/me', {'id': 'ms-506'}),
    'tiktok': ('https://open.tiktokapis.com/v2/user/info/', {'data': {'user': {'open_id': 't7'}}}),
}
ADMIN_PASSWORD = 'OAuthAdminPassword123!'


def _configure(provider, app_id=None, secret=None, active=True):
    with SessionLocal() as db:
        row = db.get(AuthProvider, provider)
        row.app_id = app_id
        row.client_secret = seal_secret(secret) if secret else None
        row.is_active = active
        db.commit()


@pytest.fixture
def site(client, monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', f'http://localhost:3000;{SITE}')
    client.cookies.clear()
    yield
    client.cookies.clear()
    for provider in [*APP_IDS, 'telegram']:
        _configure(provider, active=False)


def _mock(monkeypatch, handler):
    monkeypatch.setattr(
        oauth_providers, 'http', httpx.Client(transport=httpx.MockTransport(handler))
    )


def _start(client, provider):
    response = client.get(
        f'/auth/oauth/{provider}/start', params={'return_to': RETURN_TO}, follow_redirects=False
    )
    assert response.status_code == 302, response.text
    target = urlsplit(response.headers['location'])
    return target, {key: values[0] for key, values in parse_qs(target.query).items()}


def _finish(client, provider, params, **extra):
    response = client.get(
        f'/auth/oauth/{provider}/callback',
        params={'code': 'provider-code', 'state': params['state'], **extra},
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    back = urlsplit(response.headers['location'])
    assert f'{back.scheme}://{back.netloc}{back.path}' == f'{SITE}/auth/callback'
    return {key: values[0] for key, values in parse_qs(back.query).items()}


@pytest.mark.parametrize('provider', list(APP_IDS))
def test_redirect_sign_in_uses_each_provider_contract(client, site, monkeypatch, provider):
    _configure(provider, APP_IDS[provider], SECRET)
    spec = oauth_providers.OAUTH_PROVIDERS[provider]
    profile_url, profile = PROFILES[provider]
    seen = {}

    def handler(request):
        url = str(request.url.copy_with(query=None))
        if url == spec.token_url:
            seen['token'] = request
            return httpx.Response(200, json={'access_token': f'{provider}-token'})
        if url == 'https://api.github.com/user/emails':
            return httpx.Response(
                200, json=[{'email': 'gh@example.com', 'primary': True, 'verified': True}]
            )
        assert url == profile_url
        seen['profile'] = request
        return httpx.Response(200, json=profile)

    _mock(monkeypatch, handler)
    target, params = _start(client, provider)
    assert f'{target.scheme}://{target.netloc}{target.path}' == spec.authorize_url
    assert params[spec.client_id_param] == APP_IDS[provider]
    assert params['redirect_uri'].endswith(f'/auth/oauth/{provider}/callback')
    assert params['scope'] == spec.scope
    assert ('code_challenge' in params) == spec.pkce

    result = _finish(client, provider, params, device_id='device-1')
    assert result['next'] == '/tours'
    form = {key: values[0] for key, values in parse_qs(seen['token'].content.decode()).items()}
    assert form['code'] == 'provider-code'
    assert form['grant_type'] == 'authorization_code'
    if spec.basic_auth:
        expected = base64.b64encode(f'{APP_IDS[provider]}:{SECRET}'.encode()).decode()
        assert seen['token'].headers['authorization'] == f'Basic {expected}'
        assert 'client_secret' not in form
    else:
        assert form[spec.client_id_param] == APP_IDS[provider]
        assert form['client_secret'] == SECRET
    if spec.pkce:
        challenge = hashlib.sha256(form['code_verifier'].encode()).digest()
        assert base64.urlsafe_b64encode(challenge).rstrip(b'=').decode() == params['code_challenge']
    if provider == 'vk':
        assert form['device_id'] == 'device-1'
        assert parse_qs(seen['profile'].content.decode())['client_id'] == [APP_IDS['vk']]

    signed_in = client.post('/auth/oauth/exchange', json={'login_code': result['login_code']})
    assert signed_in.status_code == 200, signed_in.text
    token = signed_in.json()['access_token']
    me = client.get('/auth/me', headers={'Authorization': f'Bearer {token}'}).json()
    with SessionLocal() as db:
        identity = db.query(ClientIdentity).filter_by(provider=provider).one()
        assert identity.client_id == me['client_id']
    again = client.post('/auth/oauth/exchange', json={'login_code': result['login_code']})
    assert again.status_code == 401


def test_state_must_come_back_to_the_same_browser(client, site, monkeypatch):
    _configure('github', APP_IDS['github'], SECRET)
    _mock(monkeypatch, lambda request: httpx.Response(500))
    _, params = _start(client, 'github')
    client.cookies.clear()
    response = client.get(
        '/auth/oauth/github/callback',
        params={'code': 'x', 'state': params['state']},
        follow_redirects=False,
    )
    assert response.status_code == 400
    client.cookies.set('kt_oauth', 'forged')
    forged = client.get(
        '/auth/oauth/github/callback',
        params={'code': 'x', 'state': 'forged'},
        follow_redirects=False,
    )
    assert forged.status_code == 400


def test_errors_return_to_the_site_without_a_login_code(client, site, monkeypatch):
    _configure('discord', APP_IDS['discord'], SECRET)
    _mock(monkeypatch, lambda request: httpx.Response(400, json={'error': 'invalid_grant'}))
    _, params = _start(client, 'discord')
    assert _finish(client, 'discord', params) == {
        'next': '/tours',
        'login_error': 'invalid_credentials',
    }
    _, params = _start(client, 'discord')
    response = client.get(
        '/auth/oauth/discord/callback',
        params={'error': 'access_denied', 'state': params['state']},
        follow_redirects=False,
    )
    assert 'login_error=denied' in response.headers['location']


def test_start_refuses_disabled_providers_and_foreign_return_urls(client, site):
    disabled = client.get(
        '/auth/oauth/yandex/start', params={'return_to': RETURN_TO}, follow_redirects=False
    )
    assert disabled.status_code == 404
    _configure('yandex', APP_IDS['yandex'], SECRET)
    for target in ('https://evil.example/steal', f'https://user@{SITE[8:]}/x', 'javascript:1'):
        response = client.get(
            '/auth/oauth/yandex/start', params={'return_to': target}, follow_redirects=False
        )
        assert response.status_code == 400, target
    assert (
        client.get('/auth/oauth/unknown/start', params={'return_to': RETURN_TO}).status_code == 404
    )


def _telegram(bot_token, **fields):
    fields = {'id': 7001, 'first_name': 'Aibek', 'auth_date': int(time.time()), **fields}
    check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
    key = hashlib.sha256(bot_token.encode()).digest()
    return {**fields, 'hash': hmac.new(key, check.encode(), hashlib.sha256).hexdigest()}


def test_telegram_widget_signature_is_checked(client, site):
    bot_token = '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawZ'
    assert client.post('/auth/telegram', json=_telegram(bot_token)).status_code == 404
    _configure('telegram', 'KerbenTravelBot', bot_token)
    signed = client.post('/auth/telegram', json=_telegram(bot_token))
    assert signed.status_code == 200, signed.text
    tampered = {**_telegram(bot_token), 'id': 7002}
    assert client.post('/auth/telegram', json=tampered).status_code == 401
    stale = _telegram(bot_token, auth_date=int(time.time()) - 2 * 86400)
    assert client.post('/auth/telegram', json=stale).status_code == 401
    other_bot = _telegram('987654321:BBHdqTcvCH1vGWJxfSeofSAs0K5PALDsawZ')
    assert client.post('/auth/telegram', json=other_bot).status_code == 401


def test_public_list_shows_only_complete_providers(client, site):
    _configure('vk', APP_IDS['vk'], SECRET)
    _configure('x', APP_IDS['x'])
    _configure('telegram', 'KerbenTravelBot', '123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawZ')
    payload = client.get('/auth/providers').json()
    assert payload['telegram'] == {'enabled': True, 'bot': 'KerbenTravelBot'}
    assert payload['redirect'] == [
        {'provider': 'vk', 'title': 'VK ID', 'start_url': '/auth/oauth/vk/start'}
    ]


def test_secrets_are_encrypted_with_the_server_key(monkeypatch, site):
    _configure('github', APP_IDS['github'], SECRET)
    with SessionLocal() as db:
        row = db.get(AuthProvider, 'github')
        assert SECRET not in row.client_secret
        assert open_secret(row.client_secret) == SECRET
        monkeypatch.setenv('SECRET_KEY', 'another-secret-key-with-at-least-32-bytes')
        assert open_secret(row.client_secret) is None
        assert configured(row) is None


def _admin_request(client, method, path, data=None):
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username='oauth-owner').first()
        if admin is None:
            admin = Admin(
                username='oauth-owner', hashed_password=password_hash.hash(ADMIN_PASSWORD)
            )
            db.add(admin)
        admin.role = 'owner'
        admin.is_active = True
        db.commit()
    client.post('/admin/login', data={'username': 'oauth-owner', 'password': ADMIN_PASSWORD})
    try:
        return client.request(method, path, data=data, follow_redirects=False)
    finally:
        client.get('/admin/logout')


def test_admin_stores_the_secret_without_showing_it(client, site):
    missing = _admin_request(
        client,
        'POST',
        '/admin/auth-provider/edit/vk',
        {'app_id': APP_IDS['vk'], 'is_active': 'y', 'secret': '', 'save': 'Save'},
    )
    assert missing.status_code == 400
    assert 'вставьте секретный ключ' in missing.text
    saved = _admin_request(
        client,
        'POST',
        '/admin/auth-provider/edit/vk',
        {'app_id': APP_IDS['vk'], 'is_active': 'y', 'secret': SECRET, 'save': 'Save'},
    )
    assert saved.status_code in (302, 303), saved.text
    kept = _admin_request(
        client,
        'POST',
        '/admin/auth-provider/edit/vk',
        {'app_id': APP_IDS['vk'], 'is_active': 'y', 'secret': '', 'save': 'Save'},
    )
    assert kept.status_code in (302, 303)
    with SessionLocal() as db:
        assert open_secret(db.get(AuthProvider, 'vk').client_secret) == SECRET
    listing = _admin_request(client, 'GET', '/admin/auth-provider/list')
    edit = _admin_request(client, 'GET', '/admin/auth-provider/edit/vk')
    for page in (listing.text, edit.text):
        assert SECRET not in page
    assert 'сохранён' in listing.text
    assert '/auth/oauth/vk/callback' in listing.text
    google = _admin_request(
        client,
        'POST',
        '/admin/auth-provider/edit/google',
        {'app_id': '', 'is_active': '', 'secret': SECRET, 'save': 'Save'},
    )
    assert google.status_code == 400
    assert 'секрет не нужен' in google.text
