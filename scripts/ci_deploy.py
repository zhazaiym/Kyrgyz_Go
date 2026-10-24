import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request


ROOT = Path('/home/ubuntu/Kyrgyz_Go')
OVERRIDE = Path('/home/ubuntu/kyrgyzgo-deploy.override.yml')
RELEASES = Path('/home/ubuntu/releases')
BACKUPS = Path('/home/ubuntu/kyrgyzgo-backups')
ALLOWED_FILES = {'.dockerignore', 'Dockerfile', 'requirements.txt', 'main.py',
                 'create_admin.py', 'seed_demo.py', 'alembic.ini'}


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
        sensitive = any(part.startswith('.env') or part in {'__pycache__', '.git'} for part in path.parts)
        if (not allowed or path.is_absolute() or '..' in path.parts or sensitive
                or '\\' in member.name or path.suffix in {'.pem', '.key', '.db', '.pyc', '.pyo'}
                or not (member.isfile() or member.isdir())):
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
        line for line in normalized.splitlines()
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
    lines = [
        'FROM ' + base_image,
        'USER root',
    ]
    if install_requirements:
        lines.extend([
            'COPY requirements.txt /tmp/kyrgyzgo-requirements.txt',
            'RUN python -m pip install --no-cache-dir '
            '-r /tmp/kyrgyzgo-requirements.txt '
            '&& rm /tmp/kyrgyzgo-requirements.txt',
        ])
    lines.extend([
        'RUN rm -rf /app && mkdir /app && chown app:app /app',
        'COPY --chown=app:app . /app/',
        'WORKDIR /app',
        'USER app',
        command,
        '',
    ])
    return '\n'.join(lines)


def deployed_runtime_digest(name):
    path = '/app/' + name
    if name == 'Dockerfile':
        probe = (
            'import hashlib,re; from pathlib import Path; '
            + 'contents=Path(' + repr(path) + ').read_bytes().replace(b"\\r\\n",b"\\n"); '
            + 'contents=b"\\n".join(line for line in contents.splitlines() '
            + 'if not re.match(rb"^\\s*CMD\\s+",line,re.IGNORECASE)); '
            + 'print(hashlib.sha256(contents).hexdigest())'
        )
    else:
        probe = ('import hashlib; from pathlib import Path; '
                 + 'contents=Path(' + repr(path) + ').read_bytes(); '
                 + "print(hashlib.sha256(contents.replace(b'\\r\\n',b'\\n')).hexdigest())")
    return output(['sudo', '-n', 'docker', 'exec', 'kyrgyzgo_backend', 'python', '-c', probe])


def compose(*arguments):
    return run(['sudo', '-n', 'docker', 'compose', '-p', 'kyrgyz_go',
                '-f', str(ROOT / 'docker-compose.yml'), '-f', str(OVERRIDE), *arguments], cwd=ROOT)


def deploy(revision, source):
    import fcntl

    os.umask(0o077)
    with Path('/home/ubuntu/.kyrgyzgo-deploy.lock').open('a') as lock:
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
        previous = json.loads(output(['sudo', '-n', 'docker', 'inspect', 'kyrgyzgo_backend']))[0]
        if previous['State']['Health']['Status'] != 'healthy':
            raise RuntimeError('Current backend is unhealthy; manual intervention required')
        old_image = previous['Image']
        dockerfile_contents = (release / 'Dockerfile').read_bytes()
        dockerfile_cmd = dockerfile_command(dockerfile_contents)
        same_base_runtime = (
            dockerfile_cmd is not None
            and deployed_runtime_digest('Dockerfile')
            == dockerfile_runtime_digest(dockerfile_contents)
        )
        requirements_changed = (
            deployed_runtime_digest('requirements.txt')
            != runtime_digest((release / 'requirements.txt').read_bytes())
        )
        if not same_base_runtime and shutil.disk_usage(RELEASES).free < 2 * 1024 ** 3:
            raise RuntimeError('Dockerfile runtime changed: a full build needs at least 2 GiB free')
        for name in ('docker-compose.yml', 'Caddyfile', '.env'):
            shutil.copy2(ROOT / name, backup / name)
        shutil.copy2(OVERRIDE, backup / 'previous-deploy.override.yml')
        with (backup / 'database.dump').open('wb') as destination:
            run(['sudo', '-n', 'docker', 'exec', 'kyrgyzgo_postgres', 'sh', '-c',
                 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'], stdout=destination)
        with (backup / 'database.dump').open('rb') as database:
            if database.read(5) != b'PGDMP':
                raise RuntimeError('Invalid database backup')
        dockerfile = 'Dockerfile'
        if same_base_runtime:
            dockerfile = 'Dockerfile.runtime'
            (release / dockerfile).write_text(runtime_dockerfile(
                previous['Config']['Image'],
                dockerfile_cmd,
                install_requirements=requirements_changed,
            ))
        image = 'kyrgyzgo-api:' + stamp
        state = {'revision': revision, 'image': image, 'previous_image': old_image,
                 'source_directory': str(release), 'backup': str(backup), 'status': 'building'}
        state_file = backup / 'deployment-state.json'
        state_file.write_text(json.dumps(state, indent=2))
        run(['sudo', '-n', 'docker', 'build', '-f', str(release / dockerfile), '-t', image, str(release)])
        state['status'] = 'activating'
        try:
            temporary = OVERRIDE.with_suffix('.pending')
            temporary.write_text('services:\n  backend:\n    image: ' + image
                                 + '\n    build:\n      context: ' + str(release)
                                 + '\n      dockerfile: ' + dockerfile + '\n')
            temporary.replace(OVERRIDE)
            compose('config', '--quiet')
            compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', 'backend')
            with urllib.request.urlopen('https://13.53.40.37/', timeout=30) as response:
                if response.status != 200:
                    raise RuntimeError('Public HTTPS health check failed')
            state['status'] = 'healthy'
        except BaseException:
            shutil.copy2(backup / 'previous-deploy.override.yml', OVERRIDE)
            state['status'] = 'rolling_back'
            state_file.write_text(json.dumps(state, indent=2))
            compose('up', '-d', '--no-deps', '--no-build', '--wait', '--wait-timeout', '180', 'backend')
            state['status'] = 'rolled_back'
            raise
        finally:
            state_file.write_text(json.dumps(state, indent=2))
        print('DEPLOYED', revision, image, flush=True)


if __name__ == '__main__':
    deploy(revision_from_command(os.environ.get('SSH_ORIGINAL_COMMAND', '')), sys.stdin.buffer)
