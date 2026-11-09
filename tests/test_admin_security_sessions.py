from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from mysite.api.admin import SECRET_KEY, password_hash
from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.token_utils import utcnow

PASSWORD = 'SessionPassword123!'


@pytest.fixture
def security_admin():
    username = 'security_' + uuid4().hex[:14]
    with SessionLocal() as db:
        admin = Admin(username=username, hashed_password=password_hash.hash(PASSWORD))
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


def test_bad_password_and_unknown_admin_have_identical_responses(client, security_admin):
    wrong_password = sign_in(client, {**security_admin, 'password': 'incorrect'})
    unknown = sign_in(client, {**security_admin, 'username': 'missing_' + uuid4().hex[:8]})
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json() == {'code': 'invalid_credentials'}


def test_refresh_rotation_grace_returns_same_pair_then_revokes(client, security_admin, monkeypatch):
    from mysite.api import admin_sessions

    now = utcnow()
    monkeypatch.setattr(admin_sessions, 'utcnow', lambda: now)
    login = sign_in(client, security_admin).json()
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


def test_logout_revokes_access(client, security_admin):
    tokens = sign_in(client, security_admin).json()
    assert (
        client.post('/admin/logout/', json={'refresh_token': tokens['refresh_token']}).status_code
        == 204
    )
    assert client.get('/admin/me/', headers=auth(tokens)).status_code == 401


def test_password_change_revokes_sessions(client, security_admin):
    tokens = sign_in(client, security_admin).json()
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
        data={'username': security_admin['username'], 'password': PASSWORD},
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


def test_own_session_management_is_available_to_scoped_roles(client, security_admin):
    with SessionLocal() as db:
        db.get(Admin, security_admin['id']).role = 'catalog_editor'
        db.commit()
    tokens = sign_in(client, security_admin).json()
    assert client.get('/admin/sessions/', headers=auth(tokens)).status_code == 200
    assert client.get('/admin/requests/', headers=auth(tokens)).status_code == 403
    assert client.delete('/admin/sessions/not-a-uuid/', headers=auth(tokens)).status_code == 422


def test_owner_can_revoke_another_admin_session_in_sqladmin(client, admin_headers, security_admin):
    tokens = sign_in(client, security_admin).json()
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


def test_concurrent_refreshes_return_one_pair(client, security_admin):
    from concurrent.futures import ThreadPoolExecutor

    tokens = sign_in(client, security_admin).json()

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

    tokens = sign_in(client, security_admin).json()
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


def test_admin_changes_own_password_and_all_sessions_end(client, security_admin):
    first = sign_in(client, security_admin).json()
    second = sign_in(client, security_admin).json()
    new_password = 'ChangedPassword456!'

    wrong = client.post(
        '/admin/password/',
        json={'current_password': 'incorrect', 'new_password': new_password},
        headers=auth(first),
    )
    assert wrong.status_code == 401 and wrong.json() == {'code': 'invalid_credentials'}
    same = client.post(
        '/admin/password/',
        json={'current_password': PASSWORD, 'new_password': PASSWORD},
        headers=auth(first),
    )
    assert same.status_code == 422
    short = client.post(
        '/admin/password/',
        json={'current_password': PASSWORD, 'new_password': 'short'},
        headers=auth(first),
    )
    assert short.status_code == 422
    assert (
        client.post(
            '/admin/password/', json={'current_password': PASSWORD, 'new_password': new_password}
        ).status_code
        == 401
    )

    changed = client.post(
        '/admin/password/',
        json={'current_password': PASSWORD, 'new_password': new_password},
        headers=auth(first),
    )
    assert changed.status_code == 204
    for tokens in (first, second):
        assert client.get('/admin/me/', headers=auth(tokens)).status_code == 401
        refreshed = client.post(
            '/admin/token/refresh/', json={'refresh_token': tokens['refresh_token']}
        )
        assert refreshed.status_code == 401
    assert sign_in(client, security_admin).status_code == 401
    assert sign_in(client, {**security_admin, 'password': new_password}).status_code == 200
