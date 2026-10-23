import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import create_engine, inspect, text


def run_python(code: str, **environment: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(environment)
    return subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_database_url_comes_from_environment():
    expected = "sqlite:///:memory:"
    result = run_python(
        "from mysite.database.db import DATABASE_URL; print(DATABASE_URL)",
        DATABASE_URL=expected,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


def test_all_sqlalchemy_mappers_configure():
    result = run_python(
        "from sqlalchemy.orm import configure_mappers; "
        "import mysite.database.models, mysite.database.chat_models; "
        "configure_mappers(); print('ok')",
        DATABASE_URL="sqlite:///:memory:",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_empty_database_upgrades_to_alembic_head():
    database_path = Path(".test_alembic.db").resolve()
    database_url = f"sqlite:///{database_path.as_posix()}"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-m", "alembic", "upgrade", "head"],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

        engine = create_engine(database_url)
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        assert {"alembic_version", "admins", "regions", "chat_sessions"} <= tables
    finally:
        database_path.unlink(missing_ok=True)


def test_legacy_database_can_upgrade_without_recreating_tables():
    database_path = Path(".test_legacy_upgrade.db").resolve()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    try:
        legacy = subprocess.run(
            [sys.executable, "-B", "-m", "alembic", "upgrade", "15eb0352f12a"],
            cwd=os.getcwd(), env=env, capture_output=True, text=True, check=False,
        )
        assert legacy.returncode == 0, legacy.stderr
        legacy_engine = create_engine(env["DATABASE_URL"])
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text('DROP TABLE alembic_version'))
                connection.execute(text("INSERT INTO regions (name) VALUES ('Legacy fixture region')"))
        finally:
            legacy_engine.dispose()
        stamped = subprocess.run(
            [sys.executable, "-B", "-m", "alembic", "stamp", "15eb0352f12a"],
            cwd=os.getcwd(), env=env, capture_output=True, text=True, check=False,
        )
        assert stamped.returncode == 0, stamped.stderr

        upgraded = subprocess.run(
            [sys.executable, "-B", "-m", "alembic", "upgrade", "head"],
            cwd=os.getcwd(), env=env, capture_output=True, text=True, check=False,
        )
        assert upgraded.returncode == 0, upgraded.stderr

        engine = create_engine(env["DATABASE_URL"])
        try:
            columns = {
                column["name"]
                for column in inspect(engine).get_columns("regions")
            }
            with engine.connect() as connection:
                assert connection.execute(text('SELECT name FROM regions')).scalar() == 'Legacy fixture region'
        finally:
            engine.dispose()
        assert "country_id" in columns
    finally:
        database_path.unlink(missing_ok=True)
