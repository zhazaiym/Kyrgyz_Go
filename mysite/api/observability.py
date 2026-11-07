"""Low-cardinality Prometheus text metrics and a protected scrape route."""

import hmac
import os
from threading import Lock

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

router = APIRouter()
_lock = Lock()
_counters = {}
_histograms = {}
_gauges = {}

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
}
_DATABASE_OPERATIONS = {'select', 'insert', 'update', 'delete', 'ddl', 'other'}
_DATABASE_OUTCOMES = {'success', 'failure'}
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)

_COUNTER_INFO = {
    'kerben_ai_calls_total': (
        'Completed AI provider operations by operation and bounded outcome.',
        ('operation', 'outcome'),
    ),
    'kerben_chat_messages_total': ('Processed chat messages by bounded outcome.', ('outcome',)),
    'kerben_booking_conflicts_total': ('Rejected conflicting booking confirmations.', ()),
    'kerben_translation_jobs_total': ('Translation job outcomes.', ('outcome',)),
    'kerben_database_queries_total': (
        'Database statements by bounded operation and outcome.',
        ('operation', 'outcome'),
    ),
}
_HISTOGRAM_INFO = {
    'kerben_ai_call_duration_seconds': (
        'AI provider operation duration in seconds.',
        ('operation',),
    ),
    'kerben_chat_message_duration_seconds': ('Chat message duration in seconds.', ('outcome',)),
    'kerben_database_query_duration_seconds': (
        'Database statement duration in seconds.',
        ('operation',),
    ),
}
_GAUGE_INFO = {
    'kerben_websocket_connections_active': 'Currently accepted WebSocket connections.',
    'kerben_translation_queue_depth': 'In-memory translation jobs awaiting a worker.',
}


def validate_metrics_config():
    token = os.getenv('METRICS_BEARER_TOKEN', '').strip()
    if token and len(token) < 32:
        raise RuntimeError('METRICS_BEARER_TOKEN must contain at least 32 characters')
    if token.casefold().startswith('replace-with-'):
        raise RuntimeError('METRICS_BEARER_TOKEN must be a generated secret, not a placeholder')


def _labels(values):
    return tuple(sorted(values.items()))


def _increment(name, labels=(), amount=1):
    key = (name, labels)
    with _lock:
        _counters[key] = _counters.get(key, 0) + amount


def _observe(name, labels, value):
    key = (name, labels)
    with _lock:
        count, total, buckets = _histograms.get(key, (0, 0.0, [0 for _ in _DURATION_BUCKETS]))
        _histograms[key] = (
            count + 1,
            total + value,
            [current + int(value <= bound) for current, bound in zip(buckets, _DURATION_BUCKETS)],
        )


def _set_gauge(name, value):
    with _lock:
        _gauges[name] = value


def record_ai_call(operation, outcome, duration):
    if operation not in _AI_OPERATIONS or outcome not in _AI_OUTCOMES:
        raise ValueError('AI metric label is outside the bounded label set')
    labels = _labels({'operation': operation, 'outcome': outcome})
    _increment('kerben_ai_calls_total', labels)
    _observe('kerben_ai_call_duration_seconds', _labels({'operation': operation}), max(0, duration))


def record_chat_message(outcome, duration):
    if outcome not in _CHAT_OUTCOMES:
        raise ValueError('Chat metric label is outside the bounded label set')
    labels = _labels({'outcome': outcome})
    _increment('kerben_chat_messages_total', labels)
    _observe('kerben_chat_message_duration_seconds', labels, max(0, duration))


def record_booking_conflict():
    _increment('kerben_booking_conflicts_total')


def record_translation_job(outcome):
    if outcome not in _TRANSLATION_OUTCOMES:
        raise ValueError('Translation metric label is outside the bounded label set')
    _increment('kerben_translation_jobs_total', _labels({'outcome': outcome}))


def record_database_query(operation, outcome, duration):
    operation = operation.lower()
    if operation not in _DATABASE_OPERATIONS or outcome not in _DATABASE_OUTCOMES:
        raise ValueError('Database metric label is outside the bounded label set')
    _increment(
        'kerben_database_queries_total', _labels({'operation': operation, 'outcome': outcome})
    )
    _observe(
        'kerben_database_query_duration_seconds',
        _labels({'operation': operation}),
        max(0, duration),
    )


def record_websocket_connection(active):
    with _lock:
        value = _gauges.get('kerben_websocket_connections_active', 0) + (1 if active else -1)
        _gauges['kerben_websocket_connections_active'] = max(0, value)


def set_translation_queue_depth(depth):
    _set_gauge('kerben_translation_queue_depth', max(0, depth))


def refresh_process_gauges():
    from mysite.database.db import engine
    from mysite.translations.jobs import translation_queue

    pool = engine.pool
    _set_gauge('kerben_database_pool_connections{state="size"}', pool.size())
    _set_gauge('kerben_database_pool_connections{state="checked_out"}', pool.checkedout())
    _set_gauge('kerben_database_pool_connections{state="overflow"}', pool.overflow())
    _set_gauge('kerben_translation_queue_depth', translation_queue.qsize())


def _escape_label(value):
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def _render_labels(labels):
    if not labels:
        return ''
    return '{' + ','.join(f'{name}="{_escape_label(value)}"' for name, value in labels) + '}'


def render_metrics():
    lines = []
    with _lock:
        counters = dict(_counters)
        histograms = dict(_histograms)
        gauges = dict(_gauges)

    for name, (help_text, _) in _COUNTER_INFO.items():
        lines.extend((f'# HELP {name} {help_text}', f'# TYPE {name} counter'))
        for (metric, labels), value in sorted(counters.items()):
            if metric == name:
                lines.append(f'{name}{_render_labels(labels)} {value}')

    for name, (help_text, _) in _HISTOGRAM_INFO.items():
        lines.extend((f'# HELP {name} {help_text}', f'# TYPE {name} histogram'))
        for (metric, labels), (count, total, buckets) in sorted(histograms.items()):
            if metric != name:
                continue
            for bound, bucket_count in zip(_DURATION_BUCKETS, buckets):
                bucket_labels = tuple(sorted((*labels, ('le', str(bound)))))
                lines.append(f'{name}_bucket{_render_labels(bucket_labels)} {bucket_count}')
            infinity_labels = tuple(sorted((*labels, ('le', '+Inf'))))
            lines.append(f'{name}_bucket{_render_labels(infinity_labels)} {count}')
            lines.append(f'{name}_sum{_render_labels(labels)} {total:.12g}')
            lines.append(f'{name}_count{_render_labels(labels)} {count}')

    for name, help_text in _GAUGE_INFO.items():
        lines.extend((f'# HELP {name} {help_text}', f'# TYPE {name} gauge'))
        if name in gauges:
            lines.append(f'{name} {gauges[name]}')

    pool_name = 'kerben_database_pool_connections'
    lines.extend(
        (
            f'# HELP {pool_name} SQLAlchemy database pool connection counts.',
            f'# TYPE {pool_name} gauge',
        )
    )
    prefix = pool_name + '{state="'
    for key, value in sorted(gauges.items()):
        if key.startswith(prefix):
            state = key[len(prefix) :].split('"', 1)[0]
            lines.append(f'{pool_name}{{state="{state}"}} {value}')
    return '\n'.join(lines) + '\n'


def scrape_metrics():
    refresh_process_gauges()
    return render_metrics()


@router.get('/metrics', include_in_schema=False)
def metrics(authorization: str | None = Header(default=None)):
    configured = os.getenv('METRICS_BEARER_TOKEN', '').strip()
    if not configured:
        raise HTTPException(status_code=404)
    scheme, _, supplied = (authorization or '').partition(' ')
    if scheme.casefold() != 'bearer' or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=404)
    return Response(scrape_metrics(), media_type='text/plain; version=0.0.4; charset=utf-8')
