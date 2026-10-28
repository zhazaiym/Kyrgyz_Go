import importlib.util
import io
import tarfile
from pathlib import Path

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


@pytest.mark.parametrize(
    'name',
    [
        '../main.py',
        '/app/main.py',
        '.env',
        'mysite/.env',
        'mysite/secret.pem',
        '.git/config',
        'database.dump',
    ],
)
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


def test_candidate_schema_uses_alembic_configured_version_locations(tmp_path):
    module = load_deployment()
    versions = tmp_path / 'custom' / 'versions'
    versions.mkdir(parents=True)
    (versions / '001.py').write_text("revision = 'head'\ndown_revision = None\n", encoding='utf-8')
    (tmp_path / 'alembic.ini').write_text(
        '[alembic]\nscript_location = %(here)s/custom\n'
        'version_locations = %(here)s/custom/versions\n'
        'path_separator = os\n',
        encoding='utf-8',
    )

    assert module.candidate_schema(tmp_path) == ['head']


def test_candidate_schema_supports_legacy_comma_separator(tmp_path):
    module = load_deployment()
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    (first / '001.py').write_text("revision = 'first'\ndown_revision = None\n", encoding='utf-8')
    (second / '002.py').write_text(
        "revision = 'second'\ndown_revision = 'first'\n", encoding='utf-8'
    )
    (tmp_path / 'alembic.ini').write_text(
        '[alembic]\nscript_location = %(here)s\n'
        'version_locations = %(here)s/first, %(here)s/second\n',
        encoding='utf-8',
    )

    assert module.candidate_schema(tmp_path) == ['second']


@pytest.mark.parametrize('separator', ['space', 'newline'])
def test_candidate_schema_supports_legacy_named_separators(tmp_path, separator):
    module = load_deployment()
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    (first / '001.py').write_text("revision = 'first'\ndown_revision = None\n", encoding='utf-8')
    (second / '002.py').write_text(
        "revision = 'second'\ndown_revision = 'first'\n", encoding='utf-8'
    )
    locations = (
        '%(here)s/first %(here)s/second'
        if separator == 'space'
        else '%(here)s/first\n    %(here)s/second'
    )
    (tmp_path / 'alembic.ini').write_text(
        '[alembic]\nscript_location = %(here)s\n'
        f'version_locations = {locations}\nversion_path_separator = {separator}\n',
        encoding='utf-8',
    )

    assert module.candidate_schema(tmp_path) == ['second']


def test_candidate_schema_supports_package_relative_script_location(tmp_path):
    module = load_deployment()
    versions = tmp_path / 'migration_package' / 'versions'
    versions.mkdir(parents=True)
    (tmp_path / 'migration_package' / '__init__.py').write_text('', encoding='utf-8')
    (versions / '001.py').write_text(
        "revision = 'package-head'\ndown_revision = None\n", encoding='utf-8'
    )
    (tmp_path / 'alembic.ini').write_text(
        '[alembic]\nscript_location = migration_package:.\n', encoding='utf-8'
    )

    assert module.candidate_schema(tmp_path) == ['package-head']


@pytest.mark.parametrize(
    'command', ['deploy main', 'deploy ../bad', 'sh', 'deploy ' + 'a' * 40 + '; whoami']
)
def test_ssh_gateway_rejects_arbitrary_commands(command):
    with pytest.raises(ValueError):
        load_deployment().revision_from_command(command)


def test_ssh_gateway_accepts_exact_revision():
    assert load_deployment().revision_from_command('deploy ' + 'a' * 40) == 'a' * 40


def test_runtime_digest_ignores_windows_line_endings():
    module = load_deployment()
    assert module.runtime_digest(b'package==1\r\n') == module.runtime_digest(b'package==1\n')


def test_dockerfile_runtime_digest_ignores_only_command_changes():
    module = load_deployment()
    original = (
        b'FROM python:3.12-slim\nRUN pip install -r requirements.txt\nCMD ["python", "main.py"]\n'
    )
    changed_command = b'FROM python:3.12-slim\nRUN pip install -r requirements.txt\nCMD ["python", "main.py", "--safe"]\n'
    changed_runtime = (
        b'FROM python:3.13-slim\nRUN pip install -r requirements.txt\nCMD ["python", "main.py"]\n'
    )

    assert module.dockerfile_runtime_digest(original) == module.dockerfile_runtime_digest(
        changed_command
    )
    assert module.dockerfile_runtime_digest(original) != module.dockerfile_runtime_digest(
        changed_runtime
    )


def test_dockerfile_command_extracts_only_a_single_line_command():
    module = load_deployment()
    assert (
        module.dockerfile_command(b'FROM python:3.12-slim\nCMD ["python", "main.py"]\n')
        == 'CMD ["python", "main.py"]'
    )
    assert module.dockerfile_command(b'FROM python:3.12-slim\n') is None
    assert (
        module.dockerfile_command(b'FROM python:3.12-slim\nCMD \\\n  ["python", "main.py"]\n')
        is None
    )


def test_runtime_dockerfile_installs_changed_requirements_on_existing_image():
    module = load_deployment()
    command = 'CMD ["python", "main.py"]'

    incremental = module.runtime_dockerfile(
        'kyrgyzgo-api:current', command, install_requirements=True
    )
    source_only = module.runtime_dockerfile(
        'kyrgyzgo-api:current', command, install_requirements=False
    )

    assert 'FROM kyrgyzgo-api:current' in incremental
    assert 'COPY requirements.txt /tmp/kyrgyzgo-requirements.txt' in incremental
    assert 'pip install --no-cache-dir -r /tmp/kyrgyzgo-requirements.txt' in incremental
    assert command in incremental
    assert 'pip install' not in source_only
    assert command in source_only


def test_compose_override_preserves_api_service_and_production_network():
    module = load_deployment()
    override = module.compose_override('kyrgyzgo-api:ci-123')

    assert '  api:\n' in override
    assert '    image: kyrgyzgo-api:ci-123\n' in override
    assert '      - kyrgyzgo_network\n' in override
    assert '    external: true\n' in override
    assert '    name: kyrgyz_go_kyrgyzgo_network\n' in override
    assert '  backend:\n' not in override


def test_workflow_separates_tests_and_main_deployment():
    workflow = Path('.github/workflows/deploy.yml').read_text()
    assert 'pull_request:' in workflow
    assert 'needs: test' in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "github.event_name != 'pull_request'" in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    assert 'cancel-in-progress: false' in workflow
    assert 'secrets.DEPLOY_SSH_KEY' in workflow


def test_caddy_restricts_admin_routes_to_the_configured_vpn_ip_range():
    caddy = Path('Caddyfile').read_text(encoding='utf-8')
    compose = Path('docker-compose.yml').read_text(encoding='utf-8')
    example_env = Path('.env.example').read_text(encoding='utf-8')

    assert 'path /admin*' in caddy
    assert 'not remote_ip {$ADMIN_ALLOWED_CIDR}' in caddy
    assert 'respond @admin_outside_vpn 403' in caddy
    assert 'ADMIN_ALLOWED_CIDR: ${ADMIN_ALLOWED_CIDR:-127.0.0.1/32}' in compose
    assert 'ADMIN_ALLOWED_CIDR=127.0.0.1/32' in example_env
