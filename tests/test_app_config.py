import os
import subprocess
import sys

import pytest

from mysite.settings import flag, validate_settings


@pytest.mark.parametrize(
    'origin,expected_status,expected_origin',
    [
        ('https://front.example', 200, 'https://front.example'),
        ('https://admin.example', 200, 'https://admin.example'),
        ('https://kerben-travel.vercel.app', 200, 'https://kerben-travel.vercel.app'),
        ('https://untrusted.example', 400, None),
    ],
)
def test_http_cors_origins_come_from_environment(origin, expected_status, expected_origin):
    env = os.environ.copy()
    env.update(
        {
            'CORS_ALLOWED_ORIGINS': ' https://front.example ; ; https://admin.example ; '
            'https://kerben-travel.vercel.app '
        }
    )
    code = (
        'from fastapi.testclient import TestClient; '
        'from main import app; '
        'c=TestClient(app); '
        f"r=c.options('/', headers={{'Origin':{origin!r},"
        "'Access-Control-Request-Method':'GET',"
        "'Access-Control-Request-Headers':'Authorization,Content-Type'}); "
        "print(r.status_code); print(r.headers.get('access-control-allow-origin'))"
    )
    result = subprocess.run(
        [sys.executable, '-B', '-c', code],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(expected_status), str(expected_origin)]


@pytest.mark.parametrize('script', ['create_admin'])
def test_standalone_scripts_register_every_referenced_table(script):
    code = (
        f'import {script}; '
        'from mysite.database.db import Base; '
        'print(len(Base.metadata.sorted_tables))'
    )
    result = subprocess.run(
        [sys.executable, '-B', '-c', code],
        cwd=os.getcwd(),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_api_docs_can_be_hidden_on_production():
    import os
    import subprocess
    import sys

    script = (
        'from fastapi.testclient import TestClient; import main; '
        "c = TestClient(main.app); print([c.get(p).status_code for p in ('/docs', '/redoc', '/openapi.json')])"
    )
    result = subprocess.run(
        [sys.executable, '-c', script],
        env={**os.environ, 'API_DOCS': 'false'},
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert result.stdout.strip().splitlines()[-1] == '[404, 404, 404]'


@pytest.mark.parametrize(
    ('raw', 'expected'), [('1', True), (' TRUE ', True), ('off', False), ('', True)]
)
def test_flags_read_every_usual_spelling(monkeypatch, raw, expected):
    monkeypatch.setenv('ADMIN_COOKIE_SECURE', raw)
    assert flag('ADMIN_COOKIE_SECURE') is expected


@pytest.mark.parametrize(
    ('name', 'raw'),
    [
        ('API_DOCS', 'maybe'),
        ('GEMINI_REQUESTS_PER_MINUTE', 'ten'),
        ('TRIP_OPTION_RADIUS_KM', '0'),
        ('ADMIN_DOMAIN', 'https://admin.example.kg'),
    ],
)
def test_wrong_setting_stops_the_start(monkeypatch, name, raw):
    monkeypatch.setenv(name, raw)
    with pytest.raises(RuntimeError, match=name):
        validate_settings()


def test_admin_panel_moves_to_its_own_host(client, monkeypatch):
    monkeypatch.setenv('ADMIN_DOMAIN', 'admin.example.kg')
    panel = {'host': 'admin.example.kg'}
    assert client.get('/admin/login', headers=panel).status_code == 200
    root = client.get('/', headers=panel, follow_redirects=False)
    assert root.status_code == 307 and root.headers['location'] == '/admin/'
    assert client.get('/tours/', headers=panel).status_code == 404
    assert client.get('/admin/login').status_code == 404
    assert client.get('/tours/').status_code == 200
    monkeypatch.delenv('ADMIN_DOMAIN')
    assert client.get('/admin/login').status_code == 200
