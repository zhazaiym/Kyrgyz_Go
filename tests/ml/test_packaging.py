import tarfile


def test_runtime_archive_contains_ml_implementation(tmp_path):
    from scripts.manual_deploy import RUNTIME_FILES, create_archive

    for name in RUNTIME_FILES:
        (tmp_path / name).write_text('runtime', encoding='utf-8')
    for name in ('ML', 'mysite', 'scripts', 'alembic'):
        (tmp_path / name).mkdir()
        (tmp_path / name / '__init__.py').write_text('', encoding='utf-8')
    (tmp_path / 'ML' / 'agent.py').write_text('answer = 42', encoding='utf-8')
    archive = tmp_path / 'release.tar.gz'
    create_archive(tmp_path, archive)
    with tarfile.open(archive) as bundle:
        assert bundle.extractfile('ML/agent.py').read() == b'answer = 42'


def test_server_archive_validator_rejects_ml_private_files(tmp_path):
    import io

    import pytest

    from scripts.ci_deploy import validate_members

    for name in ('ML/.env', 'ML/private.key', 'ML/../secret.py'):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as bundle:
            bundle.addfile(tarfile.TarInfo(name))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as bundle, pytest.raises(ValueError):
            validate_members(bundle)
