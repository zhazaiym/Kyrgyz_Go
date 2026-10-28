import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize('secret_key', ['', 'short', 'replace-with-a-long-random-secret'])
def test_admin_api_rejects_missing_weak_and_placeholder_secrets(secret_key):
    environment = os.environ.copy()
    environment['SECRET_KEY'] = secret_key
    result = subprocess.run(
        [sys.executable, '-B', '-c', 'import mysite.api.admin'],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert 'SECRET_KEY must be' in result.stderr


def test_admin_api_accepts_a_long_non_placeholder_secret():
    environment = os.environ.copy()
    environment['SECRET_KEY'] = 'test-secret-key-for-isolated-tests'
    result = subprocess.run(
        [sys.executable, '-B', '-c', 'import mysite.api.admin'],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
