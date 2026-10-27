import os
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

from tests.postgres_support import temporary_database


def run_python(code: str, **environment: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(environment)
    return subprocess.run(
        [sys.executable, '-B', '-c', code],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_database_url_comes_from_environment():
    expected = os.environ['DATABASE_URL']
    result = run_python(
        'from mysite.database.db import DATABASE_URL; print(DATABASE_URL)', DATABASE_URL=expected
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_all_sqlalchemy_mappers_configure():
    result = run_python(
        'from sqlalchemy.orm import configure_mappers; '
        'import mysite.database.models, mysite.database.chat_models; '
        "configure_mappers(); print('ok')",
        DATABASE_URL=os.environ['DATABASE_URL'],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'ok'


def test_empty_database_upgrades_to_alembic_head():
    with temporary_database() as database_url:
        env = {**os.environ, 'DATABASE_URL': database_url}
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'alembic', 'upgrade', 'head'],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        checked = subprocess.run(
            [sys.executable, '-B', '-m', 'alembic', 'check'],
            env=env,
            capture_output=True,
            text=True,
        )
        assert checked.returncode == 0, checked.stderr
        engine = create_engine(database_url)
        try:
            tables = set(inspect(engine).get_table_names())
            assert {
                'alembic_version',
                'admins',
                'regions',
                'chat_sessions',
                'rate_limit_counters',
                'travel_selections',
            } <= tables
        finally:
            engine.dispose()


def test_legacy_database_can_upgrade_without_recreating_tables():
    with temporary_database() as database_url:
        env = {**os.environ, 'DATABASE_URL': database_url}

        def alembic(*args):
            result = subprocess.run(
                [sys.executable, '-B', '-m', 'alembic', *args],
                env=env,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr

        alembic('upgrade', '15eb0352f12a')
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(text('DROP TABLE alembic_version'))
                connection.execute(
                    text("INSERT INTO regions (name) VALUES ('Legacy fixture region')")
                )
            alembic('stamp', '15eb0352f12a')
            alembic('upgrade', 'head')
            assert 'country_id' in {col['name'] for col in inspect(engine).get_columns('regions')}
            with engine.connect() as connection:
                assert (
                    connection.scalar(text('SELECT name FROM regions')) == 'Legacy fixture region'
                )
        finally:
            engine.dispose()


@pytest.mark.parametrize('url', ['', 'sqlite:///:memory:', 'mysql://localhost/test'])
def test_missing_or_unsupported_database_is_rejected(url):
    result = run_python('import mysite.database.db', DATABASE_URL=url)
    assert result.returncode != 0
    assert 'PostgreSQL' in result.stderr
