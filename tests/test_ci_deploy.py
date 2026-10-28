import importlib.util
import io
import ipaddress
import json
import shutil
import subprocess
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


@pytest.mark.parametrize(
    ('separator', 'configured'),
    [('space', '%(here)s/first %(here)s/second'), ('newline', '%(here)s/first\n %(here)s/second')],
)
def test_candidate_schema_supports_legacy_named_version_path_separator(
    tmp_path, separator, configured
):
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
        f'version_locations = {configured}\n'
        f'version_path_separator = {separator}\n',
        encoding='utf-8',
    )

    assert module.candidate_schema(tmp_path) == ['second']


@pytest.mark.parametrize(
    ('value', 'expected', 'error'),
    [
        ('192.0.2.4,2001:db8::/32', ['192.0.2.4/32', '2001:db8::/32'], None),
        (None, None, 'must set'),
        ('', None, 'must set'),
        ('bad-network', None, 'invalid IP or network'),
        *[
            (network, None, 'too broad')
            for network in (
                '0.0.0.0/0',
                '::/0',
                '0.0.0.0/1',
                '128.0.0.0/1',
                '::/1',
                '8000::/1',
                '2000::/3',
                '10.0.0.0/8',
                '2001:db8::/31',
            )
        ],
        ('192.0.0.0/16,2001:db8::/32', ['192.0.0.0/16', '2001:db8::/32'], None),
    ],
)
def test_deploy_requires_explicit_valid_admin_allowlist(value, expected, error):
    rendered = json.dumps({'services': {'api': {'environment': {'ADMIN_ALLOWED_IPS': value}}}})
    module = load_deployment()
    if error:
        with pytest.raises(RuntimeError, match=error):
            module.validate_admin_allowlist(rendered)
    else:
        assert [str(network) for network in module.validate_admin_allowlist(rendered)] == expected


@pytest.mark.skipif(shutil.which('docker') is None, reason='Docker Compose CLI unavailable')
@pytest.mark.parametrize(
    ('content', 'override', 'expected', 'error'),
    [
        (
            'ADMIN_ALLOWED_IPS=192.0.2.1/32 # first\nADMIN_ALLOWED_IPS=198.51.100.1/32\n',
            None,
            ['198.51.100.1/32'],
            None,
        ),
        ('ADMIN_ALLOWED_IPS="192.0.2.1/32" # comment\n', None, ['192.0.2.1/32'], None),
        (
            'ADMIN_ALLOWED_IPS=192.0.2.1/32\nADMIN_ALLOWED_IPS= # cleared\n',
            None,
            None,
            'invalid IP or network',
        ),
        ('ADMIN_ALLOWED_IPS=192.0.2.1/32\nADMIN_ALLOWED_IPS=\n', None, None, 'must set'),
        (
            'ADMIN_ALLOWED_IPS=192.0.2.1/32\nexport ADMIN_ALLOWED_IPS=0.0.0.0/0\n',
            None,
            None,
            'too broad',
        ),
        (
            'ADMIN_ALLOWED_IPS=192.0.2.1/32\nexport ADMIN_ALLOWED_IPS=198.51.100.2/32\n',
            None,
            ['198.51.100.2/32'],
            None,
        ),
        ('ADMIN_ALLOWED_IPS=192.0.2.1/32\n', '203.0.113.7/32', ['203.0.113.7/32'], None),
    ],
)
def test_deploy_validates_effective_compose_admin_policy(
    tmp_path, content, override, expected, error
):
    (tmp_path / '.env').write_text(content)
    compose = 'services:\n  api:\n    image: busybox\n    env_file: [.env]\n'
    if override is not None:
        compose += f'    environment:\n      ADMIN_ALLOWED_IPS: {override}\n'
    path = tmp_path / 'compose.yml'
    path.write_text(compose)
    rendered = subprocess.check_output(
        [
            'docker',
            'compose',
            '--env-file',
            str(tmp_path / '.env'),
            '-f',
            str(path),
            'config',
            '--format',
            'json',
        ],
        text=True,
    )
    module = load_deployment()
    if error:
        with pytest.raises(RuntimeError, match=error):
            module.validate_admin_allowlist(rendered)
    else:
        assert [str(network) for network in module.validate_admin_allowlist(rendered)] == expected


@pytest.mark.parametrize('separator_key', ['path_separator', 'version_path_separator'])
def test_candidate_schema_space_separator_keeps_apostrophes_literal(tmp_path, separator_key):
    versions = tmp_path / "author's_versions"
    versions.mkdir()
    (versions / '001.py').write_text("revision = 'head'\ndown_revision = None\n")
    (tmp_path / 'alembic.ini').write_text(
        f"[alembic]\nscript_location = %(here)s\nversion_locations = %(here)s/author's_versions\n{separator_key} = space\n"
    )
    assert load_deployment().candidate_schema(tmp_path) == ['head']


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
    override = module.compose_override('kyrgyzgo-api:manual-123', '192.0.2.10/32')

    assert '  api:\n' in override
    assert '    image: kyrgyzgo-api:manual-123\n' in override
    assert '      ADMIN_ALLOWED_IPS: "192.0.2.10/32"\n' in override
    assert '      - kyrgyzgo_network\n' in override
    assert '    external: true\n' in override
    assert '    name: kyrgyz_go_kyrgyzgo_network\n' in override
    assert '  backend:\n' not in override


def test_activation_override_preserves_allowlist_and_validates_after_write(monkeypatch, tmp_path):
    module = load_deployment()
    override_path = tmp_path / 'deploy.override.yml'
    monkeypatch.setattr(module, 'OVERRIDE', override_path)
    expected_networks = [ipaddress.ip_network('192.0.2.10/32')]
    calls = []

    def compose_output(*arguments):
        assert arguments == ('config', '--format', 'json')
        assert override_path.exists()
        assert 'ADMIN_ALLOWED_IPS: "192.0.2.10/32"' in override_path.read_text()
        calls.append('resolved-config')
        return json.dumps(
            {'services': {'api': {'environment': {'ADMIN_ALLOWED_IPS': '192.0.2.10/32'}}}}
        )

    def compose(*arguments):
        calls.append(arguments)

    monkeypatch.setattr(module, 'compose_output', compose_output)
    monkeypatch.setattr(module, 'compose', compose)

    module.install_override('kyrgyzgo-api:manual-123', expected_networks)

    assert calls == ['resolved-config', ('config', '--quiet')]


def test_github_actions_runs_ci_without_deployment():
    workflow = Path('.github/workflows/ci.yml').read_text()
    assert 'pull_request:' in workflow
    assert 'branches:' in workflow and '- main' in workflow
    assert '  test:' in workflow
    assert '  deploy:' not in workflow
    assert 'DEPLOY_SSH_KEY' not in workflow
    assert 'DEPLOY_HOST' not in workflow
    assert 'docker compose up' not in workflow

    assert not Path('.github/workflows/deploy.yml').exists()
    assert not Path('.github/workflows/check-ssh.yml').exists()
