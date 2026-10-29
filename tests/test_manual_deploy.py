import importlib
import subprocess
import tarfile
from pathlib import Path

import pytest


def deployment_module():
    return importlib.import_module('scripts.manual_deploy')


def make_project(root):
    module = deployment_module()
    for name in module.RUNTIME_FILES:
        (root / name).write_text('runtime', encoding='utf-8')
    for directory in ('ML', 'mysite', 'alembic', 'scripts'):
        (root / directory).mkdir()
        (root / directory / 'source.py').write_text('value = 1', encoding='utf-8')
    (root / 'mysite' / 'source.py').write_text('uncommitted = True', encoding='utf-8')
    return module


def test_manual_archive_includes_working_tree_but_not_private_files(tmp_path):
    module = make_project(tmp_path)
    private = [
        '.env',
        'secret.pem',
        'private.key',
        'local.db',
        'local.db-wal',
        'old.pyc',
        'local.sqlite-wal',
        'local.sqlite-shm',
        'local.sqlite-journal',
        'local.sqlite3-wal',
        'local.sqlite3-shm',
        'local.sqlite3-journal',
    ]
    for directory in (tmp_path, tmp_path / 'mysite'):
        for name in private:
            (directory / name).write_text('private', encoding='utf-8')
    cache = tmp_path / 'mysite' / '__pycache__'
    cache.mkdir()
    (cache / 'cached.pyc').write_bytes(b'private')
    archive = tmp_path / 'release.tar.gz'
    module.create_archive(tmp_path, archive)
    with tarfile.open(archive) as bundle:
        names = bundle.getnames()
        assert all(Path(name).name not in private for name in names)
        assert not any('__pycache__' in name for name in names)
        assert bundle.extractfile('mysite/source.py').read() == b'uncommitted = True'


def test_manual_archive_rejects_symlinks(tmp_path, monkeypatch):
    module = make_project(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path.name == 'source.py' or original(path))
    with pytest.raises(ValueError, match='[Ss]ymlink'):
        module.create_archive(tmp_path, tmp_path / 'release.tar.gz')


def test_manual_upload_streams_binary_without_a_shell(tmp_path, monkeypatch):
    module = deployment_module()
    archive = tmp_path / 'source.tar.gz'
    archive.write_bytes(b'\x00\xff\r\n\x80')
    calls = []

    def capture(arguments, **options):
        calls.append((arguments, options, options['stdin'].read()))
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(module.subprocess, 'run', capture)
    module.upload_archive(['ssh', '-T'], archive, 'a' * 40)
    arguments, options, data = calls[0]
    assert data == b'\x00\xff\r\n\x80'
    assert not options.get('shell')
    assert 'SSH_ORIGINAL_COMMAND=' in arguments[-1]
    assert 'a' * 40 in arguments[-1]


def test_manual_ssh_pins_host_key(tmp_path):
    arguments = deployment_module().ssh_arguments('ssh', tmp_path / 'key', tmp_path / 'hosts')
    assert 'StrictHostKeyChecking=yes' in arguments
    assert 'BatchMode=yes' in arguments
    assert 'ubuntu@13.53.40.37' in arguments


def test_manual_archive_requires_runtime_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        deployment_module().create_archive(tmp_path, tmp_path / 'release.tar.gz')
