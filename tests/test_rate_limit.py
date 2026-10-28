import uuid

import pytest
from fastapi import HTTPException, Request

from mysite.api.rate_limit import (
    _blocked,
    _counter_key,
    clear_account_login_attempt,
    consume_rate_limit,
    enforce_request_limits,
)
from mysite.database.db import SessionLocal
from mysite.database.rate_limit_models import RateLimitCounter


def test_fixed_window_counter_resets_and_expires_old_keys():
    principal = uuid.uuid4().hex
    first_count, first_retry = consume_rate_limit(
        'counter-test', principal, max_requests=2, window_seconds=60, current_time=120
    )
    second_count, _ = consume_rate_limit(
        'counter-test', principal, max_requests=2, window_seconds=60, current_time=179
    )
    next_window_count, _ = consume_rate_limit(
        'counter-test', principal, max_requests=2, window_seconds=60, current_time=180
    )

    assert (first_count, first_retry) == (1, 60)
    assert second_count == 2
    assert next_window_count == 1


def test_request_limit_returns_429_for_repeated_identity(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    identity = uuid.uuid4().hex
    request = Request(
        {
            'type': 'http',
            'http_version': '1.1',
            'method': 'POST',
            'scheme': 'http',
            'path': '/auth/login',
            'headers': [],
            'client': ('198.51.100.42', 54321),
            'server': ('testserver', 80),
        }
    )

    for _ in range(2):
        enforce_request_limits(
            'login-test', request, identity, ip_limit=10, identity_limit=2, window_seconds=60
        )

    with pytest.raises(HTTPException) as limited:
        enforce_request_limits(
            'login-test', request, identity, ip_limit=10, identity_limit=2, window_seconds=60
        )

    assert limited.value.status_code == 429
    assert int(limited.value.headers['Retry-After']) > 0


def test_public_client_login_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setattr('mysite.api.rate_limit._current_epoch', lambda: 1_800_000_000)
    username = 'rate_limit_' + uuid.uuid4().hex[:12]

    responses = [
        client.post('/auth/login', json={'username': username, 'password': 'incorrect'})
        for _ in range(8)
    ]
    limited = client.post('/auth/login', json={'username': username, 'password': 'incorrect'})

    assert all(response.status_code == 401 for response in responses)
    assert limited.status_code == 429
    assert int(limited.headers['Retry-After']) > 0


def test_password_reset_clears_account_ip_counters_and_local_cooldowns():
    account_key = f'client:{uuid.uuid4().hex}'
    group_hash = _counter_key('rate-limit-group', account_key)
    addresses = ('192.0.2.10', '192.0.2.11')
    blocked = [
        ('client-login', f'account-ip:{account_key}:ip:{address}', 8, 60) for address in addresses
    ]
    with SessionLocal() as db:
        db.add_all(
            RateLimitCounter(
                key_hash=_counter_key('client-login', f'account-ip:{account_key}:ip:{address}'),
                group_hash=group_hash,
                window_start=100,
                request_count=9,
            )
            for address in addresses
        )
        db.commit()
    _blocked.update({key: 200 for key in blocked})

    with SessionLocal() as db:
        clear_account_login_attempt(db, 'client-login', account_key)
        db.commit()
        assert db.query(RateLimitCounter).filter_by(group_hash=group_hash).count() == 0

    assert all(key not in _blocked for key in blocked)
