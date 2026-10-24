import uuid

import pytest
from fastapi import HTTPException, Request

from mysite.api.rate_limit import consume_rate_limit, enforce_request_limits


def test_fixed_window_counter_resets_and_expires_old_keys():
    principal = uuid.uuid4().hex
    first_count, first_retry = consume_rate_limit(
        "counter-test", principal,
        max_requests=2, window_seconds=60, current_time=120,
    )
    second_count, _ = consume_rate_limit(
        "counter-test", principal,
        max_requests=2, window_seconds=60, current_time=179,
    )
    next_window_count, _ = consume_rate_limit(
        "counter-test", principal,
        max_requests=2, window_seconds=60, current_time=180,
    )

    assert (first_count, first_retry) == (1, 60)
    assert second_count == 2
    assert next_window_count == 1


def test_request_limit_returns_429_for_repeated_identity(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    identity = uuid.uuid4().hex
    request = Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/auth/login",
        "headers": [],
        "client": ("198.51.100.42", 54321),
        "server": ("testserver", 80),
    })

    for _ in range(2):
        enforce_request_limits(
            "login-test", request, identity,
            ip_limit=10, identity_limit=2, window_seconds=60,
        )

    with pytest.raises(HTTPException) as limited:
        enforce_request_limits(
            "login-test", request, identity,
            ip_limit=10, identity_limit=2, window_seconds=60,
        )

    assert limited.value.status_code == 429
    assert int(limited.value.headers["Retry-After"]) > 0


def test_public_client_login_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(
        "mysite.api.rate_limit._current_epoch",
        lambda: 1_800_000_000,
    )
    username = "rate_limit_" + uuid.uuid4().hex[:12]

    responses = [
        client.post(
            "/auth/login",
            json={"username": username, "password": "incorrect"},
        )
        for _ in range(8)
    ]
    limited = client.post(
        "/auth/login",
        json={"username": username, "password": "incorrect"},
    )

    assert all(response.status_code == 401 for response in responses)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
