import sys

import pytest

from scripts.run_tests import run_tests


def test_explicit_test_database_skips_docker_and_is_passed_to_pytest():
    calls = []
    environment = {'TEST_DATABASE_URL': 'postgresql://test/db', 'PATH': 'test-path'}

    def run_process(command, *, cwd, env, check):
        calls.append((command, cwd, env, check))
        return type('Result', (), {'returncode': 0})()

    exit_code = run_tests(['tests/unit', '-q'], environ=environment, run_process=run_process)

    assert exit_code == 0
    assert len(calls) == 1
    command, _, passed_environment, check = calls[0]
    assert command[:3] == [sys.executable, '-m', 'pytest']
    assert command[3:] == ['tests/unit', '-q']
    assert passed_environment['TEST_DATABASE_URL'] == 'postgresql://test/db'
    assert passed_environment['PATH'] == 'test-path'
    assert check is False


def test_compose_is_cleaned_up_after_pytest_failure():
    calls = []
    environment = {'PATH': 'test-path', 'TEST_POSTGRES_PORT': '55432'}
    codes = iter([0, 7, 0])

    def run_process(command, *, cwd, env, check):
        calls.append((command, cwd, env, check))
        return type('Result', (), {'returncode': next(codes)})()

    exit_code = run_tests(['-q'], environ=environment, run_process=run_process)

    assert exit_code == 7
    assert len(calls) == 3
    up_command, _, compose_environment, _ = calls[0]
    pytest_command, _, pytest_environment, _ = calls[1]
    down_command, _, _, _ = calls[2]
    assert up_command[-6:] == ['up', '-d', '--wait', '--wait-timeout', '90', 'postgres']
    assert compose_environment['TEST_POSTGRES_PORT'] == '55432'
    assert pytest_command[-3:] == ['-m', 'pytest', '-q']
    assert pytest_environment['TEST_DATABASE_URL'].endswith('@127.0.0.1:55432/postgres')
    assert down_command[-2:] == ['down', '--remove-orphans']
    assert environment.get('TEST_DATABASE_URL') is None


def test_compose_cleanup_failure_fails_successful_test_run():
    codes = iter([0, 0, 1])

    def run_process(command, *, cwd, env, check):
        return type('Result', (), {'returncode': next(codes)})()

    exit_code = run_tests(environ={'PATH': 'test-path'}, run_process=run_process)

    assert exit_code == 1


def test_compose_start_failure_skips_pytest_and_still_cleans_up():
    calls = []
    codes = iter([1, 0])

    def run_process(command, *, cwd, env, check):
        calls.append(command)
        return type('Result', (), {'returncode': next(codes)})()

    exit_code = run_tests(environ={'PATH': 'test-path'}, run_process=run_process)

    assert exit_code == 1
    assert len(calls) == 2
    assert calls[0][-6:] == ['up', '-d', '--wait', '--wait-timeout', '90', 'postgres']
    assert calls[1][-2:] == ['down', '--remove-orphans']


def test_compose_is_cleaned_up_when_pytest_is_interrupted():
    calls = []

    def run_process(command, *, cwd, env, check):
        calls.append(command)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return type('Result', (), {'returncode': 0})()

    with pytest.raises(KeyboardInterrupt):
        run_tests(environ={'PATH': 'test-path'}, run_process=run_process)

    assert len(calls) == 3
    assert calls[-1][-2:] == ['down', '--remove-orphans']


@pytest.mark.parametrize('port', ['not-a-port', '0', '65536'])
def test_invalid_compose_port_fails_before_running_docker(port):
    def run_process(command, *, cwd, env, check):
        raise AssertionError('Docker must not run with an invalid port')

    with pytest.raises(ValueError, match='TEST_POSTGRES_PORT'):
        run_tests(environ={'TEST_POSTGRES_PORT': port}, run_process=run_process)
