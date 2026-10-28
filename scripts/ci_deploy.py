import ast
import configparser
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path('/home/ubuntu/Kyrgyz_Go')
OVERRIDE = Path('/home/ubuntu/kyrgyzgo-deploy.override.yml')
RELEASES = Path('/home/ubuntu/releases')
BACKUPS = Path('/home/ubuntu/kyrgyzgo-backups')
DEPLOY_LOCK = Path('/home/ubuntu/.kyrgyzgo-deploy.lock')
PRODUCTION_NETWORK = 'kyrgyz_go_kyrgyzgo_network'
PRODUCTION_NETWORK_KEY = 'kyrgyzgo_network'
ALLOWED_FILES = {
    '.dockerignore',
    'Dockerfile',
    'requirements.txt',
    'main.py',
    'create_admin.py',
    'seed_demo.py',
    'alembic.ini',
}


def revision_from_command(command):
    match = re.fullmatch(r'deploy ([0-9a-f]{40})', command)
    if not match:
        raise ValueError('Only deploy followed by an exact Git commit SHA is accepted')
    return match.group(1)


def validate_members(bundle):
    members = bundle.getmembers()
    if len(members) > 5000 or sum(member.size for member in members) > 100 * 1024 * 1024:
        raise ValueError('Source archive is too large')
    for member in members:
        path = PurePosixPath(member.name)
        allowed = path.as_posix() in ALLOWED_FILES
        allowed = allowed or bool(path.parts and path.parts[0] in {'mysite', 'alembic', 'scripts'})
        sensitive = any(
            (part.startswith('.') and path.as_posix() not in ALLOWED_FILES) or part == '__pycache__'
            for part in path.parts
        )
        if (
            not allowed
            or path.is_absolute()
            or '..' in path.parts
            or sensitive
            or '\\' in member.name
            or path.suffix.lower()
            in {'.pem', '.key', '.db', '.sqlite', '.sqlite3', '.dump', '.sql', '.pyc', '.pyo'}
            or not (member.isfile() or member.isdir())
        ):
            raise ValueError('Unsafe archive member: ' + member.name)
    return members


def run(arguments, **options):
    return subprocess.run(arguments, check=True, **options)


def output(arguments):
    return subprocess.check_output(arguments, text=True).strip()


def runtime_digest(contents):
    return hashlib.sha256(contents.replace(b'\r\n', b'\n')).hexdigest()


def dockerfile_runtime_digest(contents):
    """Hash all Dockerfile instructions except CMD, which can be overridden cheaply."""
    normalized = contents.replace(b'\r\n', b'\n')
    runtime_instructions = b'\n'.join(
        line
        for line in normalized.splitlines()
        if not re.match(rb'^\s*CMD\s+', line, re.IGNORECASE)
    )
    return runtime_digest(runtime_instructions)


def dockerfile_command(contents):
    commands = [
        line.strip()
        for line in contents.replace(b'\r\n', b'\n').splitlines()
        if re.match(rb'^\s*CMD\s+', line, re.IGNORECASE)
    ]
    if len(commands) != 1 or commands[0].endswith(b'\\'):
        return None
    return commands[0].decode('utf-8')


def runtime_dockerfile(base_image, command, *, install_requirements):
    lines = ['FROM ' + base_image, 'USER root']
    if install_requirements:
        lines.extend(
            [
                'COPY requirements.txt /tmp/kyrgyzgo-requirements.txt',
                'RUN python -m pip install --no-cache-dir '
                '-r /tmp/kyrgyzgo-requirements.txt '
                '&& rm /tmp/kyrgyzgo-requirements.txt',
            ]
        )
    lines.extend(
        [
            'RUN rm -rf /app && mkdir /app && chown app:app /app',
            'COPY --chown=app:app . /app/',
            'WORKDIR /app',
            'USER app',
            command,
            '',
        ]
    )
    return '\n'.join(lines)


def deployed_runtime_digest(container, name):
    path = '/app/' + name
    if name == 'Dockerfile':
        probe = (
            'import hashlib,re; from pathlib import Path; '
            + 'source=Path('
            + repr(path)
            + '); contents=(source.read_bytes() if source.is_file() else b"").replace(b"\\r\\n",b"\\n"); '
            + 'contents=b"\\n".join(line for line in contents.splitlines() '
            + 'if not re.match(rb"^\\s*CMD\\s+",line,re.IGNORECASE)); '
            + 'print(hashlib.sha256(contents).hexdigest())'
        )
    else:
        probe = (
            'import hashlib; from pathlib import Path; '
            + 'source=Path('
            + repr(path)
            + '); contents=source.read_bytes() if source.is_file() else b""; '
            + "print(hashlib.sha256(contents.replace(b'\\r\\n',b'\\n')).hexdigest())"
        )
    return output(['sudo', '-n', 'docker', 'exec', container, 'python', '-c', probe])


def compose_override(image):
    return (
        'services:\n'
        '  api:\n'
        f'    image: {image}\n'
        f'    networks:\n'
        f'      - {PRODUCTION_NETWORK_KEY}\n'
        'networks:\n'
        f'  {PRODUCTION_NETWORK_KEY}:\n'
        '    external: true\n'
        f'    name: {PRODUCTION_NETWORK}\n'
    )


def compose(*arguments):
    return run(
        [
            'sudo',
            '-n',
            'docker',
            'compose',
            '-p',
            'kyrgyz_go',
            '-f',
            str(ROOT / 'docker-compose.yml'),
            '-f',
            str(OVERRIDE),
            *arguments,
        ],
        cwd=ROOT,
    )


def compose_output(*arguments):
    return output(
        [
            'sudo',
            '-n',
            'docker',
            'compose',
            '-p',
            'kyrgyz_go',
            '-f',
            str(ROOT / 'docker-compose.yml'),
            '-f',
            str(OVERRIDE),
            *arguments,
        ]
    )


def require_same_schema(current, candidate):
    if sorted(current) != sorted(candidate):
        raise RuntimeError(
            'Schema revision changes require a separate backed-up maintenance migration '
            'before automatic deployment. Production has not been replaced.'
        )


def deployed_schema(container):
    probe = (
        'import json; from sqlalchemy import text; from mysite.database.db import engine; '
        'connection=engine.connect(); '
        'print(json.dumps(list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()))); '
        'connection.close()'
    )
    return json.loads(output(['sudo', '-n', 'docker', 'exec', container, 'python', '-c', probe]))


def candidate_schema(source):
    source = Path(source)
    config_path = source / 'alembic.ini'
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(config_path, encoding='utf-8') or not config.has_section('alembic'):
        raise ValueError('alembic.ini has no [alembic] configuration')
    values = config['alembic']
    base = config_path.parent

    def resolve(value):
        value = value.replace('%(here)s', str(base))
        if ':' in value and not re.match(r'^[A-Za-z]:[\\/]', value):
            package, relative = value.split(':', 1)
            local_package = base.joinpath(*package.split('.'))
            if local_package.is_dir():
                return local_package / relative
            spec = importlib.util.find_spec(package)
            if spec is None:
                raise ValueError(f'Alembic package location not found: {package}')
            roots = spec.submodule_search_locations
            if roots:
                return Path(next(iter(roots))) / relative
            if spec.origin:
                return Path(spec.origin).parent / relative
            raise ValueError(f'Alembic package location has no filesystem path: {package}')
        path = Path(value)
        return path if path.is_absolute() else base / path

    script_location = resolve(values.get('script_location', 'alembic'))
    configured = values.get('version_locations')
    if configured:
        separator = values.get('path_separator')
        if separator == 'os':
            locations = configured.split(os.pathsep)
        elif separator == 'space':
            locations = shlex.split(configured)
        elif separator == 'newline':
            locations = configured.splitlines()
        elif separator:
            locations = configured.split(separator)
        elif values.get('version_path_separator') == 'os':
            locations = configured.split(os.pathsep)
        elif values.get('version_path_separator') == 'space':
            locations = shlex.split(configured)
        elif values.get('version_path_separator') == 'newline':
            locations = configured.splitlines()
        elif values.get('version_path_separator'):
            locations = configured.split(values['version_path_separator'])
        else:
            locations = re.split(r'[\s,]+', configured)
        version_paths = [resolve(item.strip()) for item in locations if item.strip()]
    else:
        version_paths = [script_location / 'versions']

    paths = []
    recursive = values.getboolean('recursive_version_locations', fallback=False)
    for directory in version_paths:
        if not directory.is_dir():
            raise ValueError(f'Alembic version directory does not exist: {directory}')
        paths.extend(directory.rglob('*.py') if recursive else directory.glob('*.py'))

    revisions = {}
    for path in paths:
        revision_values = {}
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                target = (
                    node.targets[0]
                    if isinstance(node, ast.Assign) and len(node.targets) == 1
                    else (node.target if isinstance(node, ast.AnnAssign) else None)
                )
                if isinstance(target, ast.Name) and target.id in {'revision', 'down_revision'}:
                    revision_values[target.id] = ast.literal_eval(node.value)
        revision = revision_values.get('revision')
        if not isinstance(revision, str) or revision in revisions:
            raise ValueError(f'Invalid or duplicate Alembic revision in {path.name}')
        parent = revision_values.get('down_revision')
        revisions[revision] = set(parent if isinstance(parent, (tuple, list)) else [parent]) - {
            None
        }
    known = set(revisions)
    missing = set().union(*revisions.values()) - known if revisions else set()
    if missing:
        raise ValueError(f'Alembic revisions reference missing parents: {sorted(missing)}')
    heads = known - set().union(*revisions.values()) if revisions else set()
    if not heads:
        raise ValueError('No Alembic migration head found in deployment source')
    return sorted(heads)


def deploy(revision, source):
    import fcntl

    os.umask(0o077)
    with DEPLOY_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if shutil.disk_usage(RELEASES).free < 256 * 1024 * 1024:
            raise RuntimeError('Less than 256 MiB free; increase server disk before deployment')
        stamp = 'ci-' + str(time.time_ns()) + '-' + revision[:12]
        release = RELEASES / stamp
        backup = BACKUPS / stamp
        release.mkdir()
        backup.mkdir()
        archive = backup / 'source.tar.gz'
        with archive.open('wb') as destination:
            remaining = 25 * 1024 * 1024
            while True:
                chunk = source.read(min(1024 * 1024, remaining + 1))
                if not chunk:
                    break
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError('Compressed archive exceeds 25 MiB')
                destination.write(chunk)
        with tarfile.open(archive) as bundle:
            members = validate_members(bundle)
            bundle.extractall(release, members=members, filter='data')
        if not all((release / name).is_file() for name in ALLOWED_FILES):
            raise ValueError('Archive is missing required deployment files')
        compose_output('config', '--quiet')
        run(
            ['sudo', '-n', 'docker', 'network', 'inspect', PRODUCTION_NETWORK],
            stdout=subprocess.DEVNULL,
        )
        previous_container = compose_output('ps', '-q', 'api')
        if not previous_container:
            raise RuntimeError('The production api container was not found; refusing deployment')
        previous = json.loads(output(['sudo', '-n', 'docker', 'inspect', previous_container]))[0]
        if previous['State']['Health']['Status'] != 'healthy':
            raise RuntimeError('Current api is unhealthy; manual intervention required')
        old_image_id = previous['Image']
        old_image = previous['Config']['Image']
        image = 'kyrgyzgo-api:' + stamp
        state = {
            'revision': revision,
            'image': image,
            'previous_image': old_image,
            'source_directory': str(release),
            'backup': str(backup),
            'status': 'checking_schema',
        }
        state_file = backup / 'deployment-state.json'
        state_file.write_text(json.dumps(state, indent=2))
        try:
            current_schema = deployed_schema(previous_container)
            candidate = candidate_schema(release)
        except Exception as exc:
            state['status'] = 'schema_check_failed'
            state['schema_check_error'] = f'{type(exc).__name__}: {exc}'[:500]
            state_file.write_text(json.dumps(state, indent=2))
            raise
        try:
            require_same_schema(current_schema, candidate)
        except RuntimeError:
            state['status'] = 'migration_required'
            state_file.write_text(json.dumps(state, indent=2))
            raise
        dockerfile_contents = (release / 'Dockerfile').read_bytes()
        dockerfile_cmd = dockerfile_command(dockerfile_contents)
        same_base_runtime = dockerfile_cmd is not None and deployed_runtime_digest(
            previous_container, 'Dockerfile'
        ) == dockerfile_runtime_digest(dockerfile_contents)
        requirements_changed = deployed_runtime_digest(
            previous_container, 'requirements.txt'
        ) != runtime_digest((release / 'requirements.txt').read_bytes())
        if not same_base_runtime and shutil.disk_usage(RELEASES).free < 2 * 1024**3:
            raise RuntimeError('Dockerfile runtime changed: a full build needs at least 2 GiB free')
        for name in ('docker-compose.yml', 'Caddyfile', '.env'):
            shutil.copy2(ROOT / name, backup / name)
        shutil.copy2(OVERRIDE, backup / 'previous-deploy.override.yml')
        with (backup / 'database.dump').open('wb') as destination:
            run(
                [
                    'sudo',
                    '-n',
                    'docker',
                    'exec',
                    'kyrgyzgo_postgres',
                    'sh',
                    '-c',
                    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
                ],
                stdout=destination,
            )
        with (backup / 'database.dump').open('rb') as database:
            if database.read(5) != b'PGDMP':
                raise RuntimeError('Invalid database backup')
        dockerfile = 'Dockerfile'
        if same_base_runtime:
            dockerfile = 'Dockerfile.runtime'
            (release / dockerfile).write_text(
                runtime_dockerfile(
                    old_image_id, dockerfile_cmd, install_requirements=requirements_changed
                )
            )
        state['status'] = 'building'
        state_file.write_text(json.dumps(state, indent=2))
        run(
            [
                'sudo',
                '-n',
                'docker',
                'build',
                '-f',
                str(release / dockerfile),
                '-t',
                image,
                str(release),
            ]
        )
        state['status'] = 'activating'
        try:
            temporary = OVERRIDE.with_suffix('.pending')
            temporary.write_text(compose_override(image))
            temporary.replace(OVERRIDE)
            compose('config', '--quiet')
            compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', 'api')
            with urllib.request.urlopen('https://13.53.40.37/', timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError('Public HTTPS health check failed')
            state['status'] = 'healthy'
        except BaseException:
            shutil.copy2(backup / 'previous-deploy.override.yml', OVERRIDE)
            state['status'] = 'rolling_back'
            state_file.write_text(json.dumps(state, indent=2))
            compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', 'api')
            state['status'] = 'rolled_back'
            raise
        finally:
            state_file.write_text(json.dumps(state, indent=2))
        print('DEPLOYED', revision, image, flush=True)


if __name__ == '__main__':
    deploy(revision_from_command(os.environ.get('SSH_ORIGINAL_COMMAND', '')), sys.stdin.buffer)
