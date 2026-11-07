from pathlib import Path


def test_image_ships_the_ml_package_and_runs_migrations():
    dockerfile = Path('Dockerfile').read_text(encoding='utf-8')
    assert 'COPY --chown=app:app ML ./ML' in dockerfile
    assert 'alembic upgrade head' in dockerfile


def test_image_excludes_local_secrets():
    ignored = Path('.dockerignore').read_text(encoding='utf-8').splitlines()
    assert '.env' in ignored
