from datetime import timedelta
from uuid import uuid4

import pytest

from mysite.admin.credentials import password_hash
from mysite.database.admin_security_models import AdminSession
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


def panel_login(browser, admin):
    return browser.post(
        '/admin/login',
        data={'username': admin['username'], 'password': admin['password']},
        follow_redirects=False,
    )


def test_owner_can_revoke_another_admin_session_in_sqladmin(panel, security_admin):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as browser:
        assert panel_login(browser, security_admin).status_code in (302, 303)
        assert browser.get('/admin/', follow_redirects=False).status_code == 200
        with SessionLocal() as db:
            sid = db.query(AdminSession.id).filter_by(admin_id=security_admin['id']).scalar()
        result = panel.get(
            '/admin/admin-session/action/revoke', params={'pks': sid}, follow_redirects=False
        )
        assert result.status_code == 303, result.text
        assert browser.get('/admin/', follow_redirects=False).status_code in (302, 303)


def test_owner_sets_a_password_in_the_panel_and_old_sessions_end(panel, security_admin):
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as browser:
        assert panel_login(browser, security_admin).status_code in (302, 303)
        response = panel.post(
            f'/admin/admin/edit/{security_admin["id"]}',
            data={
                'username': security_admin['username'],
                'role': 'owner',
                'is_active': 'y',
                'password': 'ChangedPassword123!',
            },
            headers={'origin': 'http://testserver'},
            follow_redirects=False,
        )
        assert response.status_code == 302, response.text
        assert browser.get('/admin/', follow_redirects=False).status_code in (302, 303)
        changed = {**security_admin, 'password': 'ChangedPassword123!'}
        assert panel_login(browser, security_admin).status_code == 400
        assert panel_login(browser, changed).status_code in (302, 303)


def test_new_administrator_needs_a_password(panel):
    response = panel.post(
        '/admin/admin/create',
        data={'username': 'nopassword_' + uuid4().hex[:8], 'role': 'manager', 'is_active': 'y'},
        headers={'origin': 'http://testserver'},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert 'Задайте пароль' in response.text
