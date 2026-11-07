import pytest

import tests.postgres_support as postgres_support
from tests.postgres_support import temporary_database


def test_database_url_is_not_accepted_as_test_database_fallback(monkeypatch):
    monkeypatch.delenv('TEST_DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///application.db')

    with pytest.raises(RuntimeError, match='TEST_DATABASE_URL'):
        temporary_database().__enter__()


def test_dotenv_database_url_is_not_accepted_as_test_database_fallback(monkeypatch):
    monkeypatch.delenv('TEST_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    dotenv_calls = []
    monkeypatch.setattr(
        postgres_support,
        'dotenv_values',
        lambda path: dotenv_calls.append(path) or {'DATABASE_URL': 'sqlite:///application.db'},
        raising=False,
    )

    with pytest.raises(RuntimeError, match='TEST_DATABASE_URL'):
        temporary_database().__enter__()

    assert dotenv_calls == []


def test_non_postgresql_test_url_is_rejected_before_connecting(monkeypatch):
    monkeypatch.setenv('TEST_DATABASE_URL', 'sqlite:///test.db')

    with pytest.raises(RuntimeError, match='TEST_DATABASE_URL.*PostgreSQL'):
        temporary_database().__enter__()
