import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pwdlib import PasswordHash


TEST_DATABASE_PATH = Path(".test_api.db").resolve()
TEST_DATABASE_PATH.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-isolated-tests")
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used-for-network-calls")

command.upgrade(Config("alembic.ini"), "head")

from main import app
from mysite.database.db import SessionLocal, engine
from mysite.database.models import Admin


@pytest.fixture(autouse=True)
def offline_catalogue_translations(monkeypatch):
    monkeypatch.setattr('mysite.translations.content.translate_fields', lambda source: {
        lang: {key: f'{value} {lang}' if value else value for key, value in source.items()}
        for lang in ('en', 'de', 'zh')
    })


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client

    engine.dispose()
    TEST_DATABASE_PATH.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def customer_headers(client):
    response = client.post('/auth/register', json={
        'username': 'catalogue_customer', 'password': 'StrongCustomerPassword123!',
    })
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


@pytest.fixture(scope="session")
def admin_headers(client):
    password = "StrongAdminPassword123!"
    with SessionLocal() as db:
        admin = db.query(Admin).filter(Admin.username == "test-admin").first()
        if admin is None:
            admin = Admin(
                username="test-admin",
                hashed_password=PasswordHash.recommended().hash(password),
                is_active=True,
            )
            db.add(admin)
            db.commit()

    response = client.post(
        "/admin/login/",
        json={"username": "test-admin", "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
