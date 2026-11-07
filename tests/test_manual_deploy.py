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


def test_ssh_accepts_explicit_deployment_target(tmp_path):
    arguments = deployment_module().ssh_arguments(
        'ssh', tmp_path / 'key', tmp_path / 'hosts', host='ubuntu@new.example.org'
    )
    assert arguments[-1] == 'ubuntu@new.example.org'
    assert 'ubuntu@13.53.40.37' not in arguments
    assert 'StrictHostKeyChecking=yes' in arguments


@pytest.mark.parametrize('target', ['-oProxyCommand=bad', 'ubuntu@host;echo bad', '', 'host'])
def test_ssh_rejects_invalid_target_before_connection(tmp_path, target):
    with pytest.raises(ValueError, match='target'):
        deployment_module().ssh_arguments('ssh', tmp_path / 'key', tmp_path / 'hosts', host=target)


def test_new_server_requires_its_own_known_hosts(tmp_path, monkeypatch, capsys):
    module = deployment_module()
    key = tmp_path / 'key'
    key.write_text('private test fixture')
    monkeypatch.setattr(
        module.sys,
        'argv',
        ['manual_deploy', '--check', '--key', str(key), '--host', 'ubuntu@new.example.org'],
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert '--known-hosts' in capsys.readouterr().err


def test_configured_deploy_packages_source_and_uses_verified_target(tmp_path, monkeypatch, capsys):
    module = deployment_module()
    key = tmp_path / 'key'
    key.write_text('private test fixture')
    hosts = tmp_path / 'hosts'
    trusted = 'new.example.org ssh-ed25519 test-public-key\n'
    hosts.write_text(trusted)
    revision = 'a' * 40
    monkeypatch.setattr(
        module.sys,
        'argv',
        [
            'manual_deploy',
            '--skip-tests',
            '--key',
            str(key),
            '--host',
            'ubuntu@new.example.org',
            '--known-hosts',
            str(hosts),
            '--revision',
            revision,
        ],
    )
    uploaded = []

    def transport(arguments, **options):
        assert arguments[-2] == 'ubuntu@new.example.org'
        host_option = next(arg for arg in arguments if arg.startswith('UserKnownHostsFile='))
        host_file = Path(host_option.split('=', 1)[1].strip('"'))
        assert host_file.read_text() == trusted
        if 'stdin' in options:
            with tarfile.open(fileobj=options['stdin'], mode='r:gz') as bundle:
                names = bundle.getnames()
                assert 'ML/tools.py' in names
                assert '.env' not in names
                assert not any(name.endswith(('.key', '.pem')) for name in names)
            assert 'deploy ' + revision in arguments[-1]
            uploaded.append(True)
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(module.subprocess, 'run', transport)
    module.main()
    assert uploaded
    assert 'DEPLOYMENT SUCCEEDED' in capsys.readouterr().out


def test_failed_preflight_never_uploads_or_reports_success(tmp_path, monkeypatch, capsys):
    module = deployment_module()
    key = tmp_path / 'key'
    key.write_text('private test fixture')
    monkeypatch.setattr(module.sys, 'argv', ['manual_deploy', '--skip-tests', '--key', str(key)])

    def fail(arguments, **options):
        assert 'stdin' not in options
        raise subprocess.CalledProcessError(255, arguments)

    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.main()
    assert 'DEPLOYMENT SUCCEEDED' not in capsys.readouterr().out


def test_manual_deploy_runs_the_isolated_test_runner(monkeypatch):
    module = deployment_module()
    root = Path(module.__file__).resolve().parents[1]
    calls = []
    monkeypatch.setattr(
        module.subprocess, 'run', lambda command, **kwargs: calls.append((command, kwargs))
    )

    module.run_local_tests(root)

    command, options = calls[0]
    assert command == [module.sys.executable, '-m', 'scripts.run_tests', '-q']
    assert options['cwd'] == root
    assert options['check'] is True


def test_manual_archive_requires_runtime_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        deployment_module().create_archive(tmp_path, tmp_path / 'release.tar.gz')
