from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect


def test_public_catalogue_keeps_http_and_websocket_chat_private(client):
    def register():
        response = client.post(
            '/auth/register',
            json={'username': 'boundary_' + uuid4().hex[:16], 'password': 'StrongPassword123!'},
        )
        assert response.status_code == 201
        return response.json()['access_token']

    owner, stranger = register(), register()
    owner_headers = {'Authorization': 'Bearer ' + owner}
    stranger_headers = {'Authorization': 'Bearer ' + stranger}
    sid = client.post('/chat/session', headers=owner_headers).json()['session_id']
    assert client.post('/chat/session').status_code == 401
    assert client.get('/chat/sessions').status_code == 401
    assert client.get(f'/chat/history/{sid}').status_code == 401
    assert client.post('/booking/preview', json={'session_id': sid}).status_code == 401
    assert client.get(f'/chat/history/{sid}', headers=stranger_headers).status_code == 404
    assert (
        client.post(
            '/booking/preview', headers=stranger_headers, json={'session_id': sid}
        ).status_code
        == 404
    )
    assert client.get(f'/chat/history/{sid}', headers=owner_headers).status_code == 200
    for frame in (
        {'type': 'message', 'text': 'guest'},
        {'type': 'auth', 'token': 'invalid'},
        {'type': 'auth', 'token': stranger},
    ):
        with client.websocket_connect(
            f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
        ) as socket:
            socket.send_json(frame)
            assert socket.receive_json()['type'] == 'error'
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 1008
