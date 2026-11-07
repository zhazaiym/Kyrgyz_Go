from itsdangerous import TimestampSigner
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from mysite.admin.setup import AdminAuthBackend


async def session_endpoint(request: Request):
    if request.url.path == '/login':
        request.session['admin_id'] = 7
        return PlainTextResponse('logged in')
    if request.url.path == '/logout':
        request.session.clear()
        return PlainTextResponse('logged out')
    return PlainTextResponse('admin' if request.session.get('admin_id') else 'login')


def test_admin_session_survives_time_and_ends_after_explicit_logout(monkeypatch):
    backend = AdminAuthBackend()
    app = Starlette(
        routes=[Route('/{path:path}', session_endpoint)], middleware=backend.middlewares
    )
    original_timestamp = TimestampSigner.get_timestamp

    with TestClient(app, base_url='https://testserver') as client:
        login = client.get('/login')
        assert 'max-age=604800' in login.headers['set-cookie'].lower()

        monkeypatch.setattr(
            TimestampSigner, 'get_timestamp', lambda signer: original_timestamp(signer) + 7200
        )
        assert client.get('/admin').text == 'admin'

        client.get('/logout')
        assert client.get('/admin').text == 'login'
