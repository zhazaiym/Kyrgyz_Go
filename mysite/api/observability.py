"""Bounded Prometheus metrics using the maintained Python client."""

import hmac
import os
import time

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

router = APIRouter()
_AI_OPERATIONS = {'extractor', 'generation', 'tool'}
_AI_OUTCOMES = {'success', 'failure', 'timeout', 'blocked'}
_CHAT_OUTCOMES = {'success', 'ai_error', 'timeout', 'conflict', 'disconnected', 'internal_error'}
_TRANSLATION_OUTCOMES = {
    'translated',
    'failed',
    'busy',
    'missing',
    'source_changed',
    'invalid_translation',
    'ai_unavailable',
    'ai_rate_limit',
    'ai_timeout',
    'ai_blocked',
    'ai_invalid_response',
}
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)


def create_metrics(registry):
    def counter(name, labels=()):
        return Counter('kerben_' + name, name.replace('_', ' '), labels, registry=registry)

    def duration(name, labels):
        return Histogram(
            'kerben_' + name,
            name.replace('_', ' '),
            labels,
            buckets=_DURATION_BUCKETS,
            registry=registry,
        )

    def gauge(name, labels=()):
        return Gauge('kerben_' + name, name.replace('_', ' '), labels, registry=registry)

    return {
        'ai': counter('ai_calls_total', ('operation', 'outcome')),
        'ai_time': duration('ai_call_duration_seconds', ('operation',)),
        'chat': counter('chat_messages_total', ('outcome',)),
        'chat_time': duration('chat_message_duration_seconds', ('outcome',)),
        'conflicts': counter('booking_conflicts_total'),
        'translations': counter('translation_jobs_total', ('outcome',)),
        'websockets': gauge('websocket_connections_active'),
        'queue': gauge('translation_queue_depth'),
        'pool': gauge('database_pool_connections', ('state',)),
        'http': counter('http_requests_total', ('method', 'route', 'status')),
        'http_time': duration('http_request_duration_seconds', ('method', 'route')),
    }


_registry = CollectorRegistry()
_metrics = create_metrics(_registry)


def validate_metrics_config():
    token = os.getenv('METRICS_BEARER_TOKEN', '').strip()
    if token and len(token) < 32:
        raise RuntimeError('METRICS_BEARER_TOKEN must contain at least 32 characters')
    if token.casefold().startswith('replace-with-'):
        raise RuntimeError('METRICS_BEARER_TOKEN must be a generated secret, not a placeholder')


def record_ai_call(operation, outcome, duration):
    if operation not in _AI_OPERATIONS or outcome not in _AI_OUTCOMES:
        raise ValueError('AI metric label is outside the bounded label set')
    _metrics['ai'].labels(operation, outcome).inc()
    _metrics['ai_time'].labels(operation).observe(max(0, duration))


def record_chat_message(outcome, duration):
    if outcome not in _CHAT_OUTCOMES:
        raise ValueError('Chat metric label is outside the bounded label set')
    _metrics['chat'].labels(outcome).inc()
    _metrics['chat_time'].labels(outcome).observe(max(0, duration))


def record_booking_conflict():
    _metrics['conflicts'].inc()


def record_translation_job(outcome):
    if outcome not in _TRANSLATION_OUTCOMES:
        raise ValueError('Translation metric label is outside the bounded label set')
    _metrics['translations'].labels(outcome).inc()


def record_websocket_connection(active):
    _metrics['websockets'].inc(1 if active else -1)


def set_translation_queue_depth(depth):
    _metrics['queue'].set(max(0, depth))


def render_metrics():
    return generate_latest(_registry).decode()


def scrape_metrics():
    from mysite.database.db import engine
    from mysite.translations.jobs import translation_queue

    for name, value in (
        ('size', engine.pool.size()),
        ('checked_out', engine.pool.checkedout()),
        ('overflow', engine.pool.overflow()),
    ):
        _metrics['pool'].labels(name).set(value)
    set_translation_queue_depth(translation_queue.qsize())
    return render_metrics()


class HTTPMetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started, status = time.perf_counter(), 500

        async def track(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, track)
        finally:
            route = getattr(scope.get('route'), 'path', '__unmatched__')
            method = (
                scope['method']
                if scope['method'] in {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
                else 'OTHER'
            )
            _metrics['http'].labels(method, route, str(status)).inc()
            _metrics['http_time'].labels(method, route).observe(time.perf_counter() - started)


@router.get('/metrics', include_in_schema=False)
def metrics(authorization: str | None = Header(default=None)):
    configured = os.getenv('METRICS_BEARER_TOKEN', '').strip()
    scheme, _, supplied = (authorization or '').partition(' ')
    if (
        not configured
        or scheme.casefold() != 'bearer'
        or not hmac.compare_digest(supplied, configured)
    ):
        raise HTTPException(status_code=404)
    return Response(scrape_metrics(), media_type='text/plain; version=0.0.4; charset=utf-8')
