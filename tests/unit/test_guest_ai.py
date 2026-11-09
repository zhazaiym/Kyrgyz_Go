from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mysite.api import guest_ai


@pytest.fixture
def guest_client(monkeypatch):
    app = FastAPI()
    app.include_router(guest_ai.guest_ai_router)
    monkeypatch.setattr(guest_ai, 'guest_quota', lambda request: None)

    def offline_client(kind):
        raise RuntimeError('Network is disabled in unit tests')

    monkeypatch.setattr(guest_ai, 'client', offline_client)
    return TestClient(app)


def test_guest_can_ask_without_token(guest_client, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            assert 'Иссык-Куль' in messages[1][1]
            return SimpleNamespace(content='Возьмите тёплую одежду.')

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    response = guest_client.post('/api/ask-ai', json={'context': {'destination': 'Иссык-Куль'}})
    assert response.status_code == 200
    assert response.json() == {'answer': 'Возьмите тёплую одежду.'}
    assert response.headers['cache-control'] == 'no-store'


def test_provider_errors_do_not_expose_secrets(guest_client, monkeypatch):
    def broken_client(kind):
        raise RuntimeError('secret-api-key')

    monkeypatch.setattr(guest_ai, 'client', broken_client)
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.status_code == 503
    assert 'secret-api-key' not in response.text


@pytest.mark.parametrize('context', [{}, {'notes': 'x' * 8001}, {'nested': {'x': 1}}])
def test_invalid_context_rejected(guest_client, context):
    assert guest_client.post('/api/ask-ai', json={'context': context}).status_code == 422


def test_quota_rejection_skips_provider(guest_client, monkeypatch):
    from fastapi import HTTPException

    def quota(request):
        raise HTTPException(429, 'rate_limited')

    monkeypatch.setattr(guest_ai, 'guest_quota', quota)
    monkeypatch.setattr(guest_ai, 'client', lambda kind: pytest.fail('Provider called'))
    assert guest_client.post('/api/ask-ai', json={'context': {'people': 2}}).status_code == 429


@pytest.mark.parametrize('context', [{'people': 2.0}, {'hotel': None}, {'notes': ['ok', 1]}])
def test_context_does_not_coerce_unsupported_types(guest_client, context):
    assert guest_client.post('/api/ask-ai', json={'context': context}).status_code == 422


def test_only_text_blocks_are_returned(guest_client, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(
                content=[
                    'First ',
                    {'type': 'text', 'text': 'second'},
                    {'type': 'tool_call', 'args': 'private-metadata'},
                ]
            )

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.json() == {'answer': 'First second'}


@pytest.mark.parametrize(
    'error_kind,status',
    [('timeout', 504), ('provider_timeout', 504), ('provider_quota', 429), ('provider_auth', 503)],
)
def test_provider_failures_are_classified(guest_client, monkeypatch, error_kind, status, caplog):
    import httpx

    class ProviderError(RuntimeError):
        code = 429 if error_kind == 'provider_quota' else 401

    class Model:
        async def ainvoke(self, messages):
            if error_kind == 'timeout':
                raise TimeoutError('private-key-in-error')
            if error_kind == 'provider_timeout':
                raise httpx.ReadTimeout('private-key-in-error')
            raise ProviderError('private-key-in-error')

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.status_code == status
    assert 'private-key-in-error' not in response.text + caplog.text


@pytest.mark.parametrize('reason', ['SAFETY', 'MAX_TOKENS'])
def test_blocked_or_truncated_answer_is_not_success(guest_client, monkeypatch, reason):
    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(
                content='partial text', response_metadata={'finish_reason': reason}
            )

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    assert guest_client.post('/api/ask-ai', json={'context': {'people': 2}}).status_code == 503


def test_limiter_failure_is_safe(guest_client, monkeypatch, caplog):
    from sqlalchemy.exc import OperationalError

    def broken_quota(request):
        raise OperationalError('private-statement', {}, RuntimeError('private-password'))

    monkeypatch.setattr(guest_ai, 'guest_quota', broken_quota)
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.status_code == 503
    assert 'private-password' not in response.text + caplog.text


def test_deadline_cancels_provider_and_releases_capacity(guest_client, monkeypatch):
    import asyncio

    from mysite.api import resource_limits

    cancelled = []

    class Model:
        async def ainvoke(self, messages):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    monkeypatch.setattr(guest_ai, 'GUEST_RESPONSE_TIMEOUT', 0.05)
    before = resource_limits._ai_active
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.status_code == 504
    assert cancelled == [True]
    assert resource_limits._ai_active == before


def test_capacity_rejects_before_provider(guest_client, monkeypatch):
    from mysite.api import resource_limits

    monkeypatch.setattr(resource_limits, '_ai_active', resource_limits.setting('AI_MAX_CONCURRENT'))
    monkeypatch.setattr(guest_ai, 'client', lambda kind: pytest.fail('Provider called'))
    response = guest_client.post('/api/ask-ai', json={'context': {'people': 2}})
    assert response.status_code == 503
    assert response.headers['retry-after'] == '5'


@pytest.mark.parametrize(
    'body',
    [
        {'context': {'x' * 81: 'value'}},
        {'context': {str(i): i for i in range(31)}},
        {'context': {'people': 2}, 'api_key': 'untrusted-extra-field'},
        {'context': []},
        {},
    ],
)
def test_request_boundaries(guest_client, body):
    assert guest_client.post('/api/ask-ai', json=body).status_code == 422


@pytest.mark.parametrize('content', ['', [], {'text': 'unsupported'}])
def test_empty_or_invalid_answer_is_safe(guest_client, monkeypatch, content):
    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=content)

    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    assert guest_client.post('/api/ask-ai', json={'context': {'people': 2}}).status_code == 503
