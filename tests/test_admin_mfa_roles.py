from time import time

from mysite.api.admin import password_hash
from mysite.api.admin_mfa import encrypt_totp_secret, generate_totp_secret, totp_code
from mysite.database.db import SessionLocal
from mysite.database.models import Admin


def _credentials(role):
    from mysite.api.admin import SECRET_KEY

    username = f'mfa-{role}'
    password = 'ScopedAdminPassword123!'
    secret = generate_totp_secret()
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if admin is None:
            admin = Admin(username=username, hashed_password=password_hash.hash(password))
            db.add(admin)
        admin.is_active = True
        admin.role = role
        admin.totp_secret_encrypted = encrypt_totp_secret(secret, SECRET_KEY)
        admin.totp_last_used_step = None
        admin.recovery_code_hashes = []
        db.commit()
    return username, password, secret


def _login(client, user):
    username, password, secret = user
    response = client.post(
        '/admin/login/',
        json={'username': username, 'password': password, 'totp_code': totp_code(secret)},
    )
    assert response.status_code == 200, response.text
    return {'Authorization': f'Bearer {response.json()["access_token"]}'}


def test_api_admin_login_requires_a_valid_second_factor(client):
    user = _credentials('manager')
    username, password, secret = user
    missing = client.post('/admin/login/', json={'username': username, 'password': password})
    now = int(time())
    valid_window_codes = {totp_code(secret, now + delta) for delta in (-30, 0, 30)}
    invalid_code = next(
        f'{value:06d}' for value in range(1_000_000) if f'{value:06d}' not in valid_window_codes
    )
    invalid = client.post(
        '/admin/login/',
        json={'username': username, 'password': password, 'totp_code': invalid_code},
    )
    valid = _login(client, (username, password, secret))
    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert client.get('/admin/me/', headers=valid).status_code == 200


def test_sqladmin_login_page_asks_for_totp_or_recovery_code(client):
    response = client.get('/admin/login')
    assert response.status_code == 200
    assert 'name="totp_code"' in response.text


def test_admin_roles_are_enforced_on_request_and_selection_routes(client):
    manager = _login(client, _credentials('manager'))
    editor = _login(client, _credentials('catalog_editor'))
    assert client.get('/admin/requests/', headers=manager).status_code == 200
    assert client.get('/manager/travel-selections/', headers=manager).status_code == 200
    assert client.get('/admin/requests/', headers=editor).status_code == 403
    assert client.get('/manager/travel-selections/', headers=editor).status_code == 403
