from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from mysite.api.admin import SECRET_KEY, password_hash
from mysite.api.admin_mfa import encrypt_totp_secret, hash_recovery_code, totp_code
from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.token_utils import utcnow

PASSWORD = 'SessionPassword123!'
SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'


@pytest.fixture
def security_admin():
    username = 'security_' + uuid4().hex[:14]
    with SessionLocal() as db:
        admin = Admin(
            username=username,
            hashed_password=password_hash.hash(PASSWORD),
            totp_secret_encrypted=encrypt_totp_secret(SECRET, SECRET_KEY),
            recovery_code_hashes=[hash_recovery_code('recovery-test-code')],
        )
        db.add(admin)
        db.commit()
        identity = admin.id
    return {'username': username, 'password': PASSWORD, 'id': identity}


def sign_in(client, admin, **kwargs):
    return client.post(
        '/admin/login/',
        json={'username': admin['username'], 'password': admin['password'], **kwargs},
    )


def auth(tokens):
    return {'Authorization': 'Bearer ' + tokens['access_token']}


def test_remembered_device_skips_mfa_but_never_password(client, security_admin):
    first = sign_in(client, security_admin, totp_code=totp_code(SECRET), remember_device=True)
    assert first.status_code == 200, first.text
    tokens = first.json()
    assert tokens.get('device_token') and tokens.get('device_id')
    assert tokens.get('refresh_token') and tokens['expires_in'] > 0
    assert sign_in(client, security_admin, device_token=tokens['device_token']).status_code == 200
    wrong = {**security_admin, 'password': 'incorrect'}
    assert sign_in(client, wrong, device_token=tokens['device_token']).json() == {
        'code': 'invalid_credentials'
    }


def test_bad_password_and_bad_mfa_have_identical_responses(client, security_admin):
    wrong_password = sign_in(client, {**security_admin, 'password': 'incorrect'})
    wrong_code = sign_in(client, security_admin, totp_code='000000')
    assert wrong_password.status_code == wrong_code.status_code == 401
    assert wrong_password.json() == wrong_code.json() == {'code': 'invalid_credentials'}


def test_refresh_rotation_grace_returns_same_pair_then_revokes(client, security_admin, monkeypatch):
    from mysite.api import admin_sessions

    now = utcnow()
    monkeypatch.setattr(admin_sessions, 'utcnow', lambda: now)
    login = sign_in(client, security_admin, totp_code=totp_code(SECRET)).json()
    old = login['refresh_token']
    refreshed = client.post('/admin/token/refresh/', json={'refresh_token': old})
    assert refreshed.status_code == 200
    rotated = refreshed.json()
    assert rotated['refresh_token'] != old
    assert client.post('/admin/token/refresh/', json={'refresh_token': old}).json() == rotated
    now += timedelta(seconds=31)
    expired = client.post('/admin/token/refresh/', json={'refresh_token': old})
    assert expired.status_code == 401 and expired.json() == {'code': 'session_expired'}
    assert client.get('/admin/me/', headers=auth(rotated)).status_code == 401


def test_logout_revokes_access_but_keeps_device(client, security_admin):
    tokens = sign_in(
        client, security_admin, totp_code=totp_code(SECRET), remember_device=True
    ).json()
    assert (
        client.post('/admin/logout/', json={'refresh_token': tokens['refresh_token']}).status_code
        == 204
    )
    assert client.get('/admin/me/', headers=auth(tokens)).status_code == 401
    assert sign_in(client, security_admin, device_token=tokens['device_token']).status_code == 200


def test_password_change_revokes_sessions_and_devices(client, security_admin):
    tokens = sign_in(
        client, security_admin, totp_code=totp_code(SECRET), remember_device=True
    ).json()
    with SessionLocal() as db:
        db.get(Admin, security_admin['id']).hashed_password = password_hash.hash(
            'ChangedPassword123!'
        )
        db.commit()
    assert client.get('/admin/me/', headers=auth(tokens)).status_code == 401
    assert (
        client.post(
            '/admin/token/refresh/', json={'refresh_token': tokens['refresh_token']}
        ).status_code
        == 401
    )
    changed = {**security_admin, 'password': 'ChangedPassword123!'}
    assert sign_in(client, changed, device_token=tokens['device_token']).status_code == 401


def test_device_is_bound_to_admin_and_can_be_revoked(client, security_admin):
    tokens = sign_in(
        client, security_admin, totp_code=totp_code(SECRET), remember_device=True
    ).json()
    with SessionLocal() as db:
        other = Admin(
            username='other_' + uuid4().hex,
            hashed_password=password_hash.hash(PASSWORD),
            totp_secret_encrypted=encrypt_totp_secret(SECRET, SECRET_KEY),
            recovery_code_hashes=[],
        )
        db.add(other)
        db.commit()
        other_name = other.username
    assert (
        sign_in(
            client, {**security_admin, 'username': other_name}, device_token=tokens['device_token']
        ).status_code
        == 401
    )
    assert (
        client.delete(
            '/admin/devices/' + tokens['device_id'] + '/', headers=auth(tokens)
        ).status_code
        == 204
    )
    assert sign_in(client, security_admin, device_token=tokens['device_token']).status_code == 401


def test_recovery_code_is_one_time_and_access_contains_session(client, security_admin):
    first = sign_in(client, security_admin, totp_code='recovery-test-code')
    assert first.status_code == 200
    payload = jwt.decode(first.json()['access_token'], SECRET_KEY, algorithms=['HS256'])
    assert payload.get('sid')
    assert sign_in(client, security_admin, totp_code='recovery-test-code').status_code == 401


def test_mfa_rollout_flag_only_allows_unenrolled_accounts_when_disabled(client, monkeypatch):
    account = {'username': 'unenrolled_' + uuid4().hex, 'password': PASSWORD}
    with SessionLocal() as db:
        db.add(
            Admin(
                username=account['username'],
                hashed_password=password_hash.hash(PASSWORD),
                recovery_code_hashes=[],
            )
        )
        db.commit()
    monkeypatch.setenv('ADMIN_MFA_REQUIRED', 'true')
    assert sign_in(client, account).status_code == 401
    monkeypatch.setenv('ADMIN_MFA_REQUIRED', 'false')
    assert sign_in(client, account).status_code == 200


def test_every_admin_api_route_declares_roles():
    from fastapi.routing import APIRoute

    from main import app
    from mysite.api.admin import get_current_admin
    from tests.test_api_permission_matrix import CATALOGUE_PREFIXES

    def calls(dependant):
        return [
            dependant.call,
            *(call for child in dependant.dependencies for call in calls(child)),
        ]

    missing = []

    def routes():
        for route in app.routes:
            if hasattr(route, 'effective_route_contexts'):
                yield from route.effective_route_contexts()
            else:
                yield route

    checked = 0
    for route in routes():
        if (
            isinstance(route, APIRoute) or hasattr(route, 'dependant')
        ) and route.dependant is not None:
            dependencies = calls(route.dependant)
            checked += get_current_admin in dependencies
            prefix = route.path.strip('/').split('/')[0]
            admin_path = route.path.startswith(('/admin/', '/manager/')) and route.path not in {
                '/admin/login/',
                '/admin/token/refresh/',
                '/admin/logout/',
            }
            catalogue_write = (
                prefix in CATALOGUE_PREFIXES
                and bool(route.methods & {'POST', 'PUT', 'PATCH', 'DELETE'})
                and '/reviews/' not in route.path
            )
            if (get_current_admin in dependencies or admin_path or catalogue_write) and not any(
                hasattr(call, 'admin_roles') for call in dependencies
            ):
                missing.append(route.path)
    assert missing == []
    assert checked > 30


def test_sqladmin_renews_active_cookie_and_expires_after_inactivity(
    client, security_admin, monkeypatch
):
    from itsdangerous import TimestampSigner

    from mysite.api import admin_sessions

    now = utcnow()
    real_timestamp = TimestampSigner.get_timestamp
    original = real_timestamp(TimestampSigner('unused'))
    offset = 0
    monkeypatch.setattr(admin_sessions, 'utcnow', lambda: now)
    monkeypatch.setattr(TimestampSigner, 'get_timestamp', lambda self: original + offset)
    response = client.post(
        '/admin/login',
        data={
            'username': security_admin['username'],
            'password': PASSWORD,
            'totp_code': totp_code(SECRET),
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert 'Max-Age=604800' in response.headers['set-cookie']
    now += timedelta(seconds=601)
    offset += 601
    active = client.get('/admin/', follow_redirects=False)
    assert active.status_code == 200
    assert 'Max-Age=604800' in active.headers['set-cookie']
    now += timedelta(days=7, seconds=1)
    offset += 7 * 86400 + 1
    assert client.get('/admin/', follow_redirects=False).status_code in (302, 303)


def test_device_expiry_and_oldest_device_eviction(client, security_admin):
    from mysite.database.admin_security_models import AdminTrustedDevice

    codes = ['device-enrollment-' + str(index) for index in range(12)]
    with SessionLocal() as db:
        db.get(Admin, security_admin['id']).recovery_code_hashes = [
            hash_recovery_code(code) for code in codes
        ]
        db.commit()
    enrolled = [
        sign_in(client, security_admin, totp_code=code, remember_device=True).json()
        for code in codes
    ]
    assert (
        sign_in(client, security_admin, device_token=enrolled[0]['device_token']).status_code == 401
    )
    with SessionLocal() as db:
        active = (
            db.query(AdminTrustedDevice)
            .filter_by(admin_id=security_admin['id'], revoked_at=None)
            .all()
        )
        assert len(active) == 10
        latest = db.get(AdminTrustedDevice, enrolled[-1]['device_id'])
        assert latest.token_hash != enrolled[-1]['device_token']
        latest.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert (
        sign_in(client, security_admin, device_token=enrolled[-1]['device_token']).status_code
        == 401
    )


def test_own_session_management_is_available_to_scoped_roles(client, security_admin):
    with SessionLocal() as db:
        db.get(Admin, security_admin['id']).role = 'catalog_editor'
        db.commit()
    tokens = sign_in(client, security_admin, totp_code=totp_code(SECRET)).json()
    assert client.get('/admin/sessions/', headers=auth(tokens)).status_code == 200
    assert client.get('/admin/devices/', headers=auth(tokens)).status_code == 200
    assert client.get('/admin/requests/', headers=auth(tokens)).status_code == 403
    assert client.delete('/admin/devices/not-a-uuid/', headers=auth(tokens)).status_code == 422
    assert client.delete('/admin/devices/', headers=auth(tokens)).status_code == 204


def test_owner_can_revoke_another_admin_session_in_sqladmin(client, admin_headers, security_admin):
    tokens = sign_in(client, security_admin, totp_code=totp_code(SECRET)).json()
    sid = jwt.decode(tokens['access_token'], SECRET_KEY, algorithms=['HS256'])['sid']
    client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )
    result = client.get(
        '/admin/admin-session/action/revoke', params={'pks': sid}, follow_redirects=False
    )
    assert result.status_code == 303, result.text
    assert client.get('/admin/me/', headers=auth(tokens)).status_code == 401


def test_sqladmin_trusted_browser_survives_logout_until_forgotten(security_admin):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app, base_url='https://testserver') as browser:
        first = browser.post(
            '/admin/login',
            data={
                'username': security_admin['username'],
                'password': PASSWORD,
                'totp_code': totp_code(SECRET),
                'remember_device': 'on',
            },
            follow_redirects=False,
        )
        assert first.status_code == 302
        cookie = first.headers.get_list('set-cookie')
        assert any(
            'kerben_admin_device=' in value and 'Secure' in value and 'HttpOnly' in value
            for value in cookie
        )
        browser.get('/admin/logout')
        assert (
            browser.post(
                '/admin/login',
                data={'username': security_admin['username'], 'password': PASSWORD},
                follow_redirects=False,
            ).status_code
            == 302
        )
        assert browser.post('/admin/forget-device', follow_redirects=False).status_code == 303
        browser.get('/admin/logout')
        assert (
            browser.post(
                '/admin/login',
                data={'username': security_admin['username'], 'password': PASSWORD},
                follow_redirects=False,
            ).status_code
            == 400
        )


def test_concurrent_refreshes_return_one_pair(client, security_admin):
    from concurrent.futures import ThreadPoolExecutor

    tokens = sign_in(client, security_admin, totp_code=totp_code(SECRET)).json()

    def refresh(_):
        response = client.post(
            '/admin/token/refresh/', json={'refresh_token': tokens['refresh_token']}
        )
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pairs = list(pool.map(refresh, range(2)))
    assert pairs[0] == pairs[1]


def test_refresh_slides_without_crossing_absolute_ninety_days(client, security_admin, monkeypatch):
    from datetime import datetime

    from mysite.api import admin_sessions
    from mysite.database.admin_security_models import AdminSession

    tokens = sign_in(client, security_admin, totp_code=totp_code(SECRET)).json()
    sid = jwt.decode(tokens['access_token'], SECRET_KEY, algorithms=['HS256'])['sid']
    now = utcnow()
    monkeypatch.setattr(admin_sessions, 'utcnow', lambda: now)
    with SessionLocal() as db:
        row = db.get(AdminSession, sid)
        row.created_at = now - timedelta(days=89)
        row.expires_at = now + timedelta(days=2)
        db.commit()
    response = client.post('/admin/token/refresh/', json={'refresh_token': tokens['refresh_token']})
    assert response.status_code == 200
    assert datetime.fromisoformat(response.json()['refresh_expires_at']) == now + timedelta(days=1)
    now += timedelta(days=2)
    assert (
        client.post(
            '/admin/token/refresh/', json={'refresh_token': response.json()['refresh_token']}
        ).status_code
        == 401
    )
