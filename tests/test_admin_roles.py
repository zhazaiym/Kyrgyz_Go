from mysite.admin.credentials import password_hash
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


def test_sqladmin_login_page_has_no_second_factor(client):
    response = client.get('/admin/login')
    assert response.status_code == 200
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert 'totp_code' not in response.text
    assert 'remember_device' not in response.text
