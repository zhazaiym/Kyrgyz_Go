import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_metric_registry():
    from mysite.api.observability import _counters, _gauges, _histograms, _lock

    with _lock:
        _counters.clear()
        _gauges.clear()
        _histograms.clear()
    yield
    with _lock:
        _counters.clear()
        _gauges.clear()
        _histograms.clear()


def test_metrics_expose_fixed_low_cardinality_labels():
    from mysite.api.observability import record_ai_call, render_metrics

    record_ai_call('generation', 'success', 0.42)
    rendered = render_metrics()

    assert 'kerben_ai_calls_total{operation="generation",outcome="success"} 1' in rendered
    assert 'kerben_ai_call_duration_seconds_count{operation="generation"} 1' in rendered
    assert 'session_id' not in rendered
    assert 'prompt' not in rendered


def test_metrics_reject_unbounded_labels():
    import pytest

    from mysite.api.observability import record_ai_call

    with pytest.raises(ValueError):
        record_ai_call('customer-123', 'success', 0.1)


def test_websocket_gauge_counts_only_active_connections():
    from mysite.api.observability import record_websocket_connection, render_metrics

    record_websocket_connection(True)
    assert 'kerben_websocket_connections_active 1' in render_metrics()
    record_websocket_connection(False)
    assert 'kerben_websocket_connections_active 0' in render_metrics()


def test_websocket_middleware_tracks_accepted_connection_lifetime():
    from mysite.api.observability import render_metrics
    from mysite.api.resource_limits import ResourceLimitsMiddleware

    outbound = []

    async def app(scope, receive, send):
        await send({'type': 'websocket.accept'})
        assert 'kerben_websocket_connections_active 1' in render_metrics()
        await send({'type': 'websocket.close', 'code': 1000})

    async def send(message):
        outbound.append(message)

    asyncio.run(
        ResourceLimitsMiddleware(app)(
            {'type': 'websocket', 'path': '/ws/chat/test', 'client': ('127.0.0.1', 12345)},
            lambda: None,
            send,
        )
    )

    assert outbound[-1]['code'] == 1000
    assert 'kerben_websocket_connections_active 0' in render_metrics()


def test_database_metrics_use_statement_categories_without_sql_labels():
    from mysite.api.observability import record_database_query, render_metrics

    record_database_query('select', 'success', 0.05)
    rendered = render_metrics()

    assert 'kerben_database_queries_total{operation="select",outcome="success"} 1' in rendered
    assert 'kerben_database_query_duration_seconds_count{operation="select"} 1' in rendered
    assert 'SELECT *' not in rendered


def test_metrics_endpoint_requires_a_configured_bearer_token(monkeypatch):
    from mysite.api.observability import router

    monkeypatch.delenv('METRICS_BEARER_TOKEN', raising=False)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        assert client.get('/metrics').status_code == 404


def test_metrics_endpoint_accepts_only_the_configured_bearer_token(monkeypatch):
    from mysite.api.observability import router

    secret = 'm' * 40
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@127.0.0.1:5432/test')
    monkeypatch.setenv('METRICS_BEARER_TOKEN', secret)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        assert client.get('/metrics', headers={'Authorization': 'Bearer wrong'}).status_code == 404
        response = client.get('/metrics', headers={'Authorization': f'Bearer {secret}'})

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/plain')
    assert 'kerben_ai_calls_total' in response.text


def test_metrics_token_must_have_sufficient_entropy(monkeypatch):
    import pytest

    from mysite.api.observability import validate_metrics_config

    monkeypatch.setenv('METRICS_BEARER_TOKEN', 'too-short')
    with pytest.raises(RuntimeError, match='at least 32 characters'):
        validate_metrics_config()


def test_metrics_token_rejects_documentation_placeholder(monkeypatch):
    import pytest

    from mysite.api.observability import validate_metrics_config

    monkeypatch.setenv(
        'METRICS_BEARER_TOKEN', 'replace-with-a-random-token-of-at-least-32-characters'
    )
    with pytest.raises(RuntimeError, match='not a placeholder'):
        validate_metrics_config()
