"""Run tests with an explicit PostgreSQL database or a disposable Compose service."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / 'docker-compose.test.yml'


def _run(command, *, environment, run_process):
    try:
        result = run_process(command, cwd=ROOT, env=environment, check=False)
    except OSError as exc:
        print(f'Could not run {command[0]!r}: {exc}', file=sys.stderr)
        return 127
    return result.returncode


def _postgres_port(environment):
    raw_port = environment.get('TEST_POSTGRES_PORT', '55432')
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError('TEST_POSTGRES_PORT must be an integer from 1 to 65535') from exc
    if not 1 <= port <= 65535:
        raise ValueError('TEST_POSTGRES_PORT must be an integer from 1 to 65535')
    return port


def run_tests(pytest_args=None, *, environ=None, run_process=None):
    """Run pytest, creating and cleaning a disposable PostgreSQL service if needed."""
    environment = dict(os.environ if environ is None else environ)
    execute = subprocess.run if run_process is None else run_process
    pytest_command = [sys.executable, '-m', 'pytest', *(pytest_args or [])]

    if environment.get('TEST_DATABASE_URL'):
        return _run(pytest_command, environment=environment, run_process=execute)

    port = _postgres_port(environment)
    compose_environment = dict(environment)
    compose_environment['TEST_POSTGRES_PORT'] = str(port)
    project = f'kyrgyzgo-tests-{uuid.uuid4().hex[:12]}'
    compose_command = ['docker', 'compose', '--project-name', project, '--file', str(COMPOSE_FILE)]
    setup_command = [*compose_command, 'up', '-d', '--wait', '--wait-timeout', '90', 'postgres']
    cleanup_command = [*compose_command, 'down', '--remove-orphans']

    exit_code = 1
    cleanup_code = 0
    try:
        exit_code = _run(setup_command, environment=compose_environment, run_process=execute)
        if exit_code:
            print(f'Test PostgreSQL failed to start (exit code {exit_code}).', file=sys.stderr)
        else:
            test_environment = dict(environment)
            test_environment['TEST_DATABASE_URL'] = (
                f'postgresql+psycopg2://postgres:postgres@127.0.0.1:{port}/postgres'
            )
            exit_code = _run(pytest_command, environment=test_environment, run_process=execute)
    finally:
        cleanup_code = _run(cleanup_command, environment=compose_environment, run_process=execute)
    if cleanup_code:
        print(f'Test PostgreSQL cleanup failed (exit code {cleanup_code}).', file=sys.stderr)
        if not exit_code:
            exit_code = cleanup_code
    return exit_code


def main():
    try:
        return run_tests(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
