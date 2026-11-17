import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import TimeoutError as DatabasePoolTimeout

from mysite.api import resource_limits
from mysite.api.errors import database_busy_response


def test_full_database_pool_answers_503_with_retry(client):
    import main

    assert main.app.exception_handlers[DatabasePoolTimeout] is database_busy_response
    response = asyncio.run(database_busy_response(None, DatabasePoolTimeout()))
    assert response.status_code == 503
    assert response.headers['Retry-After'] == '2'


async def _upload(pauses):
    pieces = iter(pauses)
    sent = []

    async def receive():
        pause = next(pieces, None)
        if pause is None:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        await asyncio.sleep(pause)
        return {'type': 'http.request', 'body': b'x' * 100, 'more_body': True}

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        while (await receive()).get('more_body'):
            pass
        await send({'type': 'http.response.start', 'status': 201, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})

    scope = {
        'type': 'http',
        'method': 'POST',
        'path': '/chat/images',
        'query_string': b'',
        'headers': [],
        'client': ('203.0.113.9', 1000),
        'scheme': 'http',
    }
    middleware = resource_limits.ResourceLimitsMiddleware(app)
    try:
        await middleware(scope, receive, send)
    except HTTPException as refused:  # in the application FastAPI turns it into the response
        return refused.status_code
    return next(m['status'] for m in sent if m['type'] == 'http.response.start')


@pytest.mark.parametrize(('pauses', 'status'), [([0.4, 0.4, 0.4], 201), ([1.5], 408)])
def test_upload_may_be_slow_but_not_silent(monkeypatch, pauses, status):
    monkeypatch.setenv('REQUEST_BODY_TIMEOUT', '1')
    resource_limits.setting.cache_clear()
    try:
        assert asyncio.run(_upload(pauses)) == status
    finally:
        resource_limits.setting.cache_clear()
