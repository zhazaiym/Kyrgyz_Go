from mysite.api.admin import password_hash
from mysite.database.db import SessionLocal
from mysite.database.models import Admin


def _credentials(role):
    username = f'role-{role}'
    password = 'ScopedAdminPassword123!'
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if admin is None:
            admin = Admin(username=username, hashed_password=password_hash.hash(password))
            db.add(admin)
        admin.is_active = True
        admin.role = role
        db.commit()
    return username, password


def _login(client, user):
    username, password = user
    response = client.post('/admin/login/', json={'username': username, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f'Bearer {response.json()["access_token"]}'}


def test_api_admin_login_needs_only_username_and_password(client):
    username, password = _credentials('manager')
    wrong = client.post('/admin/login/', json={'username': username, 'password': 'Wrong12345!'})
    assert wrong.status_code == 401
    assert wrong.json() == {'code': 'invalid_credentials'}
    headers = _login(client, (username, password))
    assert client.get('/admin/me/', headers=headers).status_code == 200


def test_sqladmin_login_page_has_no_second_factor(client):
    response = client.get('/admin/login')
    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert 'totp_code' not in response.text
    assert 'remember_device' not in response.text


def test_admin_roles_are_enforced_on_request_and_selection_routes(client):
    manager = _login(client, _credentials('manager'))
    editor = _login(client, _credentials('catalog_editor'))
    assert client.get('/admin/requests/', headers=manager).status_code == 200
    assert client.get('/manager/travel-selections/', headers=manager).status_code == 200
    assert client.get('/admin/requests/', headers=editor).status_code == 403
    assert client.get('/manager/travel-selections/', headers=editor).status_code == 403
