import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    'origin,expected_status,expected_origin',
    [
        ('https://front.example', 200, 'https://front.example'),
        ('https://admin.example', 200, 'https://admin.example'),
        ('https://kyrgyzgo-admin.vercel.app', 200, 'https://kyrgyzgo-admin.vercel.app'),
        ('https://untrusted.example', 400, None),
    ],
)
def test_http_cors_origins_come_from_environment(origin, expected_status, expected_origin):
    env = os.environ.copy()
    env.update(
        {
            'CORS_ALLOWED_ORIGINS': ' https://front.example ; ; https://admin.example ; '
            'https://kyrgyzgo-admin.vercel.app '
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


@pytest.mark.parametrize('script', ['create_admin', 'seed_demo'])
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
