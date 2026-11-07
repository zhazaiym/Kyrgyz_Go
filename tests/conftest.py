# ruff: noqa: E402 -- configure the isolated test database before importing the app.
import atexit
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from alembic import command
from alembic.config import Config
from tests.postgres_support import temporary_database

_TEST_TOTP_SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'


class MFAAwareTestClient(TestClient):
    def post(self, url, *args, **kwargs):
        if url in ('/admin/login', '/admin/login/') and isinstance(kwargs.get('data'), dict):
            from mysite.api.admin_mfa import totp_code
            from mysite.database.db import SessionLocal
            from mysite.database.models import Admin

            username = kwargs['data'].get('username')
            if username == 'test-admin':
                with SessionLocal() as db:
                    admin = db.query(Admin).filter_by(username=username).first()
                    if admin is not None:
                        admin.totp_last_used_step = None
                        db.commit()

            kwargs['data'].setdefault('totp_code', totp_code(_TEST_TOTP_SECRET))
        return super().post(url, *args, **kwargs)


_test_database = temporary_database()
os.environ['DATABASE_URL'] = _test_database.__enter__()


def _cleanup_database():
    from mysite.database.db import engine

    engine.dispose()
    _test_database.__exit__(None, None, None)


atexit.register(_cleanup_database)
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-isolated-tests')
os.environ.setdefault('GEMINI_API_KEY', 'test-key-not-used-for-network-calls')
os.environ.setdefault('ADMIN_ALLOWED_IPS', '127.0.0.1/32,::1/128')
os.environ['ADMIN_COOKIE_SECURE'] = 'false'
_media_root = tempfile.TemporaryDirectory()
atexit.register(_media_root.cleanup)
os.environ['MEDIA_ROOT'] = _media_root.name

command.upgrade(Config('alembic.ini'), 'head')

from main import app
from mysite.database.db import SessionLocal, engine
from mysite.database.models import Admin


@pytest.fixture(autouse=True)
def offline_catalogue_translations(monkeypatch):
    from mysite.api.resource_limits import setting, validate_resource_settings

    setting.cache_clear()
    validate_resource_settings.cache_clear()
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'false')
    monkeypatch.setattr(
        'mysite.translations.content.translate_fields',
        lambda source: {
            lang: {key: f'{value} {lang}' if value else value for key, value in source.items()}
            for lang in ('en', 'de', 'zh')
        },
    )
    monkeypatch.setattr('mysite.translations.jobs.recover_missing_translations', lambda: 0)
    monkeypatch.setattr(
        'mysite.translations.translator.translate_fields',
        lambda source: {
            lang: {key: f'{value} {lang}' if value else value for key, value in source.items()}
            for lang in ('en', 'de', 'zh')
        },
    )
    from mysite.translations.jobs import translate_record

    monkeypatch.setattr(
        'mysite.translations.jobs.enqueue_translation',
        lambda entity, identity, source, translator: (
            translate_record(entity, identity, source, translator) == 'translated'
        ),
    )
    monkeypatch.setattr(
        'mysite.admin.views.enqueue_translation',
        lambda entity, identity, source, translator: (
            translate_record(entity, identity, source, translator) == 'translated'
        ),
    )
    monkeypatch.setattr(
        'mysite.api.tour.translate_tour',
        lambda source: {
            lang: {key: f'{value} {lang}' if value else value for key, value in source.items()}
            for lang in ('en', 'de', 'zh')
        },
    )
    yield
    setting.cache_clear()
    validate_resource_settings.cache_clear()


@pytest.fixture(scope='session')
def client():
    with MFAAwareTestClient(app, client=('127.0.0.1', 50000)) as test_client:
        yield test_client

    engine.dispose()


@pytest.fixture(scope='session')
def customer_headers(client):
    response = client.post(
        '/auth/register',
        json={'username': 'catalogue_customer', 'password': 'StrongCustomerPassword123!'},
    )
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


@pytest.fixture(scope='session')
def admin_headers(client):
    password = 'StrongAdminPassword123!'
    with SessionLocal() as db:
        admin = db.query(Admin).filter(Admin.username == 'test-admin').first()
        if admin is None:
            admin = Admin(
                username='test-admin',
                hashed_password=PasswordHash.recommended().hash(password),
                is_active=True,
            )
            db.add(admin)
        from mysite.api.admin import SECRET_KEY
        from mysite.api.admin_mfa import encrypt_totp_secret

        admin.role = 'owner'
        admin.totp_secret_encrypted = encrypt_totp_secret(_TEST_TOTP_SECRET, SECRET_KEY)
        admin.totp_last_used_step = None
        admin.recovery_code_hashes = []
        db.commit()

    from mysite.api.admin_mfa import totp_code

    response = client.post(
        '/admin/login/',
        json={
            'username': 'test-admin',
            'password': password,
            'totp_code': totp_code(_TEST_TOTP_SECRET),
        },
    )
    assert response.status_code == 200, response.text
    return {'Authorization': f'Bearer {response.json()["access_token"]}'}
