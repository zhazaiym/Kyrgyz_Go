from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from mysite.api.origin_config import configured_origins


def test_configured_origins_normalizes_semicolon_list(monkeypatch):
    monkeypatch.setenv(
        'CORS_ALLOWED_ORIGINS',
        'https://kyrgyzgo-admin.vercel.app; https://tours-app-teal.vercel.app; ;',
    )
    origins = configured_origins('CORS_ALLOWED_ORIGINS', 'http://localhost:3000')
    assert origins == ('https://kyrgyzgo-admin.vercel.app', 'https://tours-app-teal.vercel.app')

    app = FastAPI()

    @app.get('/ping')
    def ping():
        return PlainTextResponse('pong')

    app.add_middleware(CORSMiddleware, allow_origins=list(origins), allow_credentials=True)
    response = TestClient(app).options(
        '/ping',
        headers={
            'Origin': 'https://tours-app-teal.vercel.app',
            'Access-Control-Request-Method': 'GET',
        },
    )
    assert response.headers['access-control-allow-origin'] == 'https://tours-app-teal.vercel.app'


def test_chat_websocket_accepts_configured_frontend_origin(client, customer_headers, monkeypatch):
    import pytest
    from starlette.websockets import WebSocketDisconnect

    session = client.post('/chat/session', headers=customer_headers)
    assert session.status_code == 200, session.text
    monkeypatch.setenv('CHAT_ALLOWED_ORIGINS', 'https://tours-app-teal.vercel.app')

    with client.websocket_connect(
        f'/ws/chat/{session.json()["session_id"]}',
        headers={'origin': 'https://tours-app-teal.vercel.app'},
    ) as socket:
        socket.send_json({'type': 'auth', 'token': customer_headers['Authorization'].split()[1]})
        assert socket.receive_json()['type'] == 'connected'

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f'/ws/chat/{session.json()["session_id"]}', headers={'origin': 'https://evil.example'}
        ):
            pass
