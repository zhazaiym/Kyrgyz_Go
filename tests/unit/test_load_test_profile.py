import pytest

from scripts.load_test import validate_database_host, validate_profile


def test_load_harness_defaults_to_stub_provider():
    validate_profile(users=4, messages=2, provider_mode='stub')


@pytest.mark.parametrize(
    ('users', 'messages', 'mode'),
    [(0, 1, 'stub'), (9, 1, 'stub'), (1, 11, 'stub'), (1, 1, 'remote')],
)
def test_load_harness_rejects_unsafe_profiles(users, messages, mode):
    with pytest.raises(ValueError):
        validate_profile(users, messages, mode)


def test_live_gemini_requires_opt_in_and_is_capped_to_one_message():
    with pytest.raises(ValueError, match='requires --live-gemini'):
        validate_profile(1, 1, 'live-gemini')
    validate_profile(1, 1, 'live-gemini', allow_live=True)
    with pytest.raises(ValueError, match='capped at one user'):
        validate_profile(2, 1, 'live-gemini', allow_live=True)


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost', '::1'])
def test_load_harness_accepts_loopback_postgresql_only(host):
    host_part = f'[{host}]' if ':' in host else host
    validate_database_host(f'postgresql+psycopg2://tester:secret@{host_part}:5432/postgres')


def test_load_harness_rejects_remote_postgresql_hosts():
    with pytest.raises(ValueError, match='host must be local'):
        validate_database_host('postgresql+psycopg2://tester:secret@database.example:5432/postgres')
