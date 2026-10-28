import asyncio

from mysite.api.admin_access import AdminAccessMiddleware, _allowed_networks
from mysite.api.network_identity import client_network


def test_environment_example_keeps_local_admin_fallback(monkeypatch):
    from dotenv import dotenv_values

    assert 'ADMIN_ALLOWED_IPS' not in dotenv_values('.env.example')
    monkeypatch.delenv('ADMIN_ALLOWED_IPS', raising=False)
    assert [str(network) for network in _allowed_networks()] == ['127.0.0.1/32', '::1/128']


def test_invalid_admin_allowlist_fails_closed_without_disabling_public_paths(monkeypatch):
    monkeypatch.setenv('ADMIN_ALLOWED_IPS', 'not-a-network')
    assert _allowed_networks() == ()
    reached = []

    async def app(scope, receive, send):
        reached.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    middleware = AdminAccessMiddleware(app)

    async def run(path):
        messages = []

        async def send(message):
            messages.append(message)

        await middleware(
            {'type': 'http', 'path': path, 'client': ('127.0.0.1', 1234)}, lambda: None, send
        )
        return messages[0]['status']

    assert asyncio.run(run('/admin/login')) == 403
    assert asyncio.run(run('/health')) == 200
    assert reached == ['/health']


def test_admin_allowlist_normalizes_ipv4_mapped_ipv6(monkeypatch):
    monkeypatch.setenv('ADMIN_ALLOWED_IPS', '127.0.0.1/32')
    reached = []

    async def app(scope, receive, send):
        reached.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    messages = []

    async def send(message):
        messages.append(message)

    assert client_network('::ffff:127.0.0.1') == '127.0.0.1'
    asyncio.run(
        AdminAccessMiddleware(app)(
            {'type': 'http', 'path': '/admin/login', 'client': ('::ffff:127.0.0.1', 1234)},
            lambda: None,
            send,
        )
    )
    assert messages[0]['status'] == 200
    assert reached == ['/admin/login']


def test_admin_allowlist_accepts_native_ipv6_network_identity(monkeypatch):
    monkeypatch.setenv('ADMIN_ALLOWED_IPS', '2001:db8:abcd::/64')
    reached = []

    async def app(scope, receive, send):
        reached.append(scope['path'])
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(
        AdminAccessMiddleware(app)(
            {'type': 'http', 'path': '/admin/login', 'client': ('2001:db8:abcd::1234', 1234)},
            lambda: None,
            send,
        )
    )
    assert messages[0]['status'] == 200
    assert reached == ['/admin/login']
