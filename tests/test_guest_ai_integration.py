"""Guest HTTP contract with the real app and PostgreSQL limiter, offline AI."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app
from mysite.api import guest_ai, rate_limit


def test_guest_ip_quota_and_authenticated_chat_boundary(monkeypatch):
    calls = []

    class Model:
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content='Travel advice')

    # Separate limiter scopes keep this test independent of all other quotas.
    original = guest_ai.enforce_rate_limit
    suffix = uuid4().hex[:8]

    def quota(scope, principal, **kwargs):
        return original(scope + suffix, principal, **kwargs)

    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setattr(guest_ai, 'enforce_rate_limit', quota)
    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    with TestClient(app, client=('192.0.2.51', 51000)) as http:
        for _ in range(5):
            response = http.post('/api/ask-ai', json={'context': {'people': 2}})
            assert response.status_code == 200
            assert response.json() == {'answer': 'Travel advice'}
            assert response.headers['cache-control'] == 'no-store'
        limited = http.post('/api/ask-ai', json={'context': {'people': 2}})
        assert limited.status_code == 429
        assert int(limited.headers['retry-after']) > 0
        assert len(calls) == 5
        for method, path in [
            ('post', '/chat/session'),
            ('get', '/chat/sessions'),
            ('get', '/chat/history/unknown'),
            ('post', '/booking/confirm'),
        ]:
            assert http.request(method, path, json={}).status_code == 401


def test_global_guest_quota_applies_across_networks(monkeypatch):
    from mysite.database.db import SessionLocal
    from mysite.database.rate_limit_models import RateLimitCounter

    original = guest_ai.enforce_rate_limit
    scope = 'guest-global-test-' + uuid4().hex[:8]
    instant = rate_limit._current_epoch()
    with SessionLocal() as db:
        db.add(
            RateLimitCounter(
                key_hash=rate_limit._counter_key(scope, 'all'),
                scope=scope,
                window_start=instant // 3600 * 3600,
                request_count=100,
            )
        )
        db.commit()

    def quota(name, principal, **kwargs):
        if name == 'guest-ai-global':
            return original(scope, principal, **kwargs)

    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setattr(guest_ai, 'enforce_rate_limit', quota)
    monkeypatch.setattr(
        guest_ai, 'client', lambda kind: (_ for _ in ()).throw(AssertionError('Provider called'))
    )
    with TestClient(app, client=('192.0.2.52', 51000)) as http:
        response = http.post('/api/ask-ai', json={'context': {'people': 2}})
        assert response.status_code == 429
        assert response.json()['detail']['code'] == 'rate_limited'


def test_openapi_guest_contract_matches_documentation(client):
    spec = client.get('/openapi.json').json()
    operation = spec['paths']['/api/ask-ai']['post']
    assert not operation.get('security')
    schema = spec['components']['schemas']['GuestQuestion']
    assert schema['required'] == ['context']
    assert schema['additionalProperties'] is False
    context = schema['properties']['context']
    assert context['minProperties'] == 1 and context['maxProperties'] == 30
    assert spec['components']['schemas']['GuestAnswer']['required'] == ['answer']
