import importlib.util
import io
from pathlib import Path
import tarfile

import pytest


SCRIPT = Path('scripts/ci_deploy.py')


def load_deployment():
    spec = importlib.util.spec_from_file_location('ci_deploy', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive(name, kind=tarfile.REGTYPE):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as bundle:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
        member.size = 1 if kind == tarfile.REGTYPE else 0
        bundle.addfile(member, io.BytesIO(b'x') if member.size else None)
    output.seek(0)
    return output


@pytest.mark.parametrize('name', ['../main.py', '/app/main.py', '.env', 'mysite/.env',
                                  'mysite/secret.pem', '.git/config', 'database.dump'])
def test_deployment_rejects_unsafe_archive_members(name):
    module = load_deployment()
    with tarfile.open(fileobj=make_archive(name)) as bundle:
        with pytest.raises(ValueError):
            module.validate_members(bundle)


def test_deployment_rejects_symlinks():
    module = load_deployment()
    with tarfile.open(fileobj=make_archive('mysite/link', tarfile.SYMTYPE)) as bundle:
        with pytest.raises(ValueError):
            module.validate_members(bundle)


def test_deployment_accepts_source_files():
    module = load_deployment()
    with tarfile.open(fileobj=make_archive('mysite/chain/prompts.py')) as bundle:
        assert len(module.validate_members(bundle)) == 1


@pytest.mark.parametrize('command', ['deploy main', 'deploy ../bad', 'sh',
                                     'deploy ' + 'a' * 40 + '; whoami'])
def test_ssh_gateway_rejects_arbitrary_commands(command):
    with pytest.raises(ValueError):
        load_deployment().revision_from_command(command)


def test_ssh_gateway_accepts_exact_revision():
    assert load_deployment().revision_from_command('deploy ' + 'a' * 40) == 'a' * 40


def test_runtime_digest_ignores_windows_line_endings():
    module = load_deployment()
    assert module.runtime_digest(b'package==1\r\n') == module.runtime_digest(b'package==1\n')


def test_workflow_separates_tests_and_main_deployment():
    workflow = Path('.github/workflows/deploy.yml').read_text()
    assert 'pull_request:' in workflow
    assert 'needs: test' in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.event_name != 'pull_request'" in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert 'secrets.DEPLOY_SSH_KEY' in workflow
