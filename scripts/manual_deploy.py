import argparse
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

from .ci_deploy import ALLOWED_FILES, validate_members

RUNTIME_FILES = tuple(sorted(ALLOWED_FILES))
HOST = 'ubuntu@13.53.40.37'
HOST_KEY = (
    '13.53.40.37 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPgDjdsROqk/hlhi8y+IUEgOouCvGWamJkQH7n1tFpSo\n'
)
DATABASE_SUFFIXES = tuple(
    extension + sidecar
    for extension in ('.db', '.sqlite', '.sqlite3')
    for sidecar in ('', '-wal', '-shm', '-journal')
)
PRIVATE_SUFFIXES = ('.pem', '.key', '.pyc', '.pyo', '.dump', '.sql', *DATABASE_SUFFIXES)


def create_archive(root, destination):
    paths = []
    for name in RUNTIME_FILES:
        path = root / name
        if path.is_symlink():
            raise ValueError('Symlink is not allowed: ' + name)
        if not path.is_file():
            raise FileNotFoundError('Missing runtime file: ' + name)
        paths.append(path)
    for name in ('mysite', 'alembic', 'scripts'):
        directory = root / name
        if directory.is_symlink():
            raise ValueError('Symlink is not allowed: ' + name)
        if not directory.is_dir():
            raise FileNotFoundError('Missing source directory: ' + name)
        for path in sorted(directory.rglob('*')):
            relative = path.relative_to(root)
            if any(part == '__pycache__' or part.startswith('.') for part in relative.parts):
                continue
            if path.name.lower().endswith(PRIVATE_SUFFIXES):
                continue
            if path.is_symlink():
                raise ValueError('Symlink is not allowed: ' + str(relative))
            if path.is_file():
                paths.append(path)
    with tarfile.open(destination, 'w:gz') as bundle:
        for path in paths:
            bundle.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    if destination.stat().st_size > 25 * 1024 * 1024:
        raise ValueError('Source archive exceeds the server limit of 25 MiB')
    with tarfile.open(destination) as bundle:
        validate_members(bundle)


def ssh_arguments(executable, key, known_hosts):
    return [
        str(executable),
        '-T',
        '-i',
        str(key),
        '-o',
        'BatchMode=yes',
        '-o',
        'StrictHostKeyChecking=yes',
        '-o',
        'UserKnownHostsFile="' + known_hosts.as_posix() + '"',
        '-o',
        'ConnectTimeout=20',
        '-o',
        'ServerAliveInterval=15',
        '-o',
        'ServerAliveCountMax=20',
        HOST,
    ]


def upload_archive(arguments, archive, snapshot):
    if not re.fullmatch('[0-9a-f]{40}', snapshot):
        raise ValueError('Invalid snapshot digest')
    command = (
        'SSH_ORIGINAL_COMMAND='
        + shlex.quote('deploy ' + snapshot)
        + ' /usr/bin/python3 /usr/local/lib/kyrgyzgo/ci_deploy.py'
    )
    with archive.open('rb') as source:
        subprocess.run([*arguments, command], stdin=source, check=True)


def main():
    parser = argparse.ArgumentParser(description='Upload the working source tree directly over SSH')
    parser.add_argument('--key', type=Path, default=Path.home() / '.ssh/kyrgyzgo_ec2_deploy')
    parser.add_argument(
        '--check', action='store_true', help='Validate packaging and SSH without deployment'
    )
    parser.add_argument('--skip-tests', action='store_true', help='Explicitly skip local tests')
    options = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    key = options.key.expanduser().resolve()
    if not key.is_file():
        parser.error('SSH private key not found: ' + str(key))
    if os.name == 'nt':
        executable = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/OpenSSH/ssh.exe'
        if not executable.is_file():
            parser.error('Windows OpenSSH client is not installed')
    else:
        executable = shutil.which('ssh')
        if not executable:
            parser.error('OpenSSH client is not installed')
    if not options.check and not options.skip_tests:
        cache = root / '.pytest_cache'
        cache.mkdir(exist_ok=True)
        subprocess.run(
            [
                sys.executable,
                '-m',
                'pytest',
                '-q',
                '--basetemp=' + str(cache / ('manual-' + uuid.uuid4().hex)),
            ],
            cwd=root,
            check=True,
        )
    with tempfile.TemporaryDirectory(prefix='kyrgyzgo-deploy-') as temporary:
        archive = Path(temporary) / 'source.tar.gz'
        known_hosts = Path(temporary) / 'known_hosts'
        known_hosts.write_text(HOST_KEY, encoding='ascii')
        create_archive(root, archive)
        snapshot = hashlib.sha256(archive.read_bytes()).hexdigest()[:40]
        arguments = ssh_arguments(executable, key, known_hosts)
        print('Source snapshot:', snapshot, flush=True)
        preflight = (
            'test -r /usr/local/lib/kyrgyzgo/ci_deploy.py && '
            "test \"$(sudo -n docker inspect --format '{{.State.Health.Status}}' "
            'kyrgyzgo_backend)" = healthy && df -h /'
        )
        subprocess.run([*arguments, preflight], check=True)
        if options.check:
            print('CHECK PASSED: source archive and SSH validated; no deployment performed.')
            return
        upload_archive(arguments, archive, snapshot)
        print('DEPLOYMENT SUCCEEDED: backend is healthy at https://13.53.40.37')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('Deployment stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
