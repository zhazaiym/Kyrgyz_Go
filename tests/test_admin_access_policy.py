import asyncio

import pytest

from mysite.api.admin_access import AdminAccessMiddleware


@pytest.mark.parametrize('scope_type', ['http', 'websocket'])
def test_admin_access_is_not_restricted_by_source_ip(monkeypatch, scope_type):
    monkeypatch.setenv('ADMIN_ALLOWED_IPS', '127.0.0.1/32')
    reached = []
    messages = []

    async def app(scope, receive, send):
        reached.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 401, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'login required'})

    async def send(message):
        messages.append(message)

    asyncio.run(
        AdminAccessMiddleware(app)(
            {'type': scope_type, 'path': '/admin/me/', 'client': ('198.51.100.40', 50000)},
            lambda: None,
            send,
        )
    )
    assert reached == ['/admin/me/']
    assert messages[0]['status'] == 401
