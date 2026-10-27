import uuid

import pytest
from fastapi import HTTPException

from mysite.api import chat_service
from mysite.database.chat_models import ChatMessage, ChatSession
from mysite.database.db import SessionLocal


@pytest.mark.parametrize(
    'payload',
    [
        "' OR '1'='1",
        '1; DROP TABLE chat_clients;--',
        "' UNION SELECT password_hash FROM chat_clients--",
    ],
)
def test_sql_injection_payloads_are_rejected_or_treated_as_values(client, payload):
    registration = client.post(
        '/auth/register', json={'username': payload, 'password': 'StrongPassword123!'}
    )
    assert registration.status_code == 422

    login = client.post('/auth/login', json={'username': payload, 'password': 'StrongPassword123!'})
    assert login.status_code == 401

    numeric_path = client.get(f'/tours/category/{payload}/')
    assert numeric_path.status_code == 422


def test_stale_chat_worker_cannot_overwrite_newer_session_state(client):
    username = 'concurrency_' + uuid.uuid4().hex[:16]
    registered = client.post(
        '/auth/register', json={'username': username, 'password': 'StrongPassword123!'}
    )
    assert registered.status_code == 201, registered.text
    token = registered.json()['access_token']
    client_id = registered.json()['client_id']

    created = client.post('/chat/session', headers={'Authorization': f'Bearer {token}'})
    assert created.status_code == 200, created.text
    session_id = created.json()['session_id']

    first = chat_service._prepare_message(session_id, client_id, token, 'first turn')
    stale = chat_service._prepare_message(session_id, client_id, token, 'stale turn')
    assert first[3] == stale[3]

    chat_service._save_message_response(
        session_id,
        client_id,
        token,
        first[3],
        first[4],
        'first response',
        {'client_name': 'First'},
        first[1],
        False,
    )

    with pytest.raises(HTTPException) as conflict:
        chat_service._save_message_response(
            session_id,
            client_id,
            token,
            stale[3],
            stale[4],
            'stale response',
            {'client_name': 'Stale'},
            stale[1],
            False,
        )

    assert conflict.value.status_code == 409
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        assert session.state == {'client_name': 'First'}
        assert session.message_version == first[3] + 1
        stale_message = db.query(ChatMessage).filter_by(id=stale[4]).first()
        assert stale_message is None
