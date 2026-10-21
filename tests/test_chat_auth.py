import asyncio
import threading
import time

import pytest

from mysite.database.chat_models import ChatSession
from mysite.database.db import SessionLocal


def test_session_creation_respects_foreign_keys(client):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from main import app
    from mysite.database.db import Base, get_db

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    try:
        token = register(client, "chat_foreign_keys")
        response = client.post("/chat/session", headers=bearer(token))
        assert response.status_code == 200
        history = client.get(
            f"/chat/history/{response.json()['session_id']}", headers=bearer(token)
        )
        assert history.status_code == 200
        assert [message["role"] for message in history.json()] == ["assistant"]
        assert history.json()[0]["content"] == response.json()["welcome"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def register(client, username):
    response = client.post(
        "/chat/auth/register",
        json={"username": username, "password": "StrongPassword123!"},
    )
    assert response.status_code == 201, response.text
    return response.json()["access_token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_chat_sessions_are_owned_by_the_authenticated_client(client):
    first_token = register(client, "chat_owner")
    second_token = register(client, "chat_other")

    created = client.post("/chat/session", headers=bearer(first_token))
    assert created.status_code == 200, created.text
    session_id = created.json()["session_id"]

    assert client.get(
        f"/chat/history/{session_id}", headers=bearer(first_token)
    ).status_code == 200
    assert client.get(
        f"/chat/history/{session_id}", headers=bearer(second_token)
    ).status_code == 404


def test_chat_logout_revokes_the_login_token(client):
    token = register(client, "chat_logout")
    assert client.get("/chat/auth/me", headers=bearer(token)).status_code == 200
    assert client.post("/chat/auth/logout", headers=bearer(token)).status_code == 200
    assert client.get("/chat/auth/me", headers=bearer(token)).status_code == 401


def test_booking_confirmation_is_idempotent(client):
    token = register(client, "chat_booking")
    session_response = client.post("/chat/session", headers=bearer(token))
    session_id = session_response.json()["session_id"]

    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        session.state = {
            "client_name": "Booking User",
            "phone": "+996700000002",
            "people_count": 2,
            "travel_date": "2099-06-01",
            "destination": "Иссык-Куль",
        }
        session.stage = "awaiting_confirmation"
        session.revision = 1
        db.commit()

    payload = {"session_id": session_id, "revision": 1, "confirmed": True}
    first = client.post("/booking/confirm", json=payload, headers=bearer(token))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "submitted"

    second = client.post("/booking/confirm", json=payload, headers=bearer(token))
    assert second.status_code == 200, second.text
    assert second.json() == {
        "status": "already_submitted",
        "request_id": first.json()["request_id"],
        "client_code": first.json()["client_code"],
    }


def test_websocket_authentication_accepts_owned_session(client):
    token = register(client, "chat_socket")
    created = client.post("/chat/session", headers=bearer(token))
    session_id = created.json()["session_id"]

    with client.websocket_connect(
        f"/ws/chat/{session_id}",
        headers={"origin": "http://localhost:3000"},
    ) as websocket:
        websocket.send_json({"type": "auth", "token": token})
        assert websocket.receive_json() == {
            "type": "connected",
            "session_id": session_id,
        }


@pytest.mark.parametrize('operation', ['authentication', 'message', 'confirmation'])
def test_chat_database_wait_does_not_block_event_loop(client, monkeypatch, operation):
    from fastapi import HTTPException, WebSocketDisconnect
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from mysite.api import chat_service, chat_ws
    from mysite.database.db import engine

    token = register(client, f'chat_pool_{operation}')
    client_id = client.get('/chat/auth/me', headers=bearer(token)).json()['client_id']
    session_id = client.post('/chat/session', headers=bearer(token)).json()['session_id']
    limited_engine = create_engine(
        engine.url, pool_size=1, max_overflow=0, pool_timeout=3,
        connect_args={'check_same_thread': False},
    )
    sessions = sessionmaker(bind=limited_engine, autoflush=False)
    monkeypatch.setattr(chat_service, 'SessionLocal', sessions)
    monkeypatch.setattr(chat_ws, 'SessionLocal', sessions)

    async def offline_reply(message, state, history, on_chunk=None):
        return 'Test response', state, False

    monkeypatch.setattr(chat_service, 'respond', offline_reply)

    class Socket:
        headers = {'origin': 'http://localhost:3000'}

        def __init__(self):
            self.received = False
            self.sent = []

        async def accept(self):
            pass

        async def receive_json(self):
            if self.received:
                raise WebSocketDisconnect()
            self.received = True
            return {'type': 'auth', 'token': token}

        async def send_json(self, data):
            self.sent.append(data)

        async def close(self, code):
            pass

    socket = Socket()
    held = limited_engine.connect()
    release = threading.Timer(0.6, held.close)

    async def run():
        started = time.monotonic()

        async def heartbeat():
            await asyncio.sleep(0.05)
            return time.monotonic() - started

        if operation == 'authentication':
            task = chat_ws.socket(socket, session_id)
        elif operation == 'message':
            task = chat_service.process_message(session_id, client_id, token, 'Hello')
        else:
            task = chat_service.confirm_booking_serialized(session_id, client_id, token, 0, False)
        release.start()
        result, delay = await asyncio.gather(task, heartbeat(), return_exceptions=True)
        assert delay < 0.3, f'Database checkout blocked the event loop for {delay:.2f}s'
        if operation == 'confirmation':
            assert isinstance(result, HTTPException) and result.status_code == 400
        elif operation == 'message':
            assert result['answer'] == 'Test response'
        else:
            assert result is None
            assert socket.sent[0]['type'] == 'connected'

    try:
        asyncio.run(run())
    finally:
        release.join()
        held.close()
        limited_engine.dispose()


def test_cancelled_chat_write_keeps_session_serialized(client, monkeypatch):
    from mysite.api import chat_service
    from mysite.database.chat_models import ChatMessage

    token = register(client, 'chat_cancelled_write')
    client_id = client.get('/chat/auth/me', headers=bearer(token)).json()['client_id']
    session_id = client.post('/chat/session', headers=bearer(token)).json()['session_id']
    entered = threading.Event()
    release = threading.Event()
    save = chat_service._save_message_response

    def paused_save(*args):
        entered.set()
        assert release.wait(timeout=3)
        return save(*args)

    async def offline_reply(message, state, history, on_chunk=None):
        return 'Test response', state, False

    monkeypatch.setattr(chat_service, '_save_message_response', paused_save)
    monkeypatch.setattr(chat_service, 'respond', offline_reply)

    async def run():
        first = asyncio.create_task(chat_service.process_message(
            session_id, client_id, token, 'First request'))
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            first.cancel()
            second = asyncio.create_task(chat_service.process_message(
                session_id, client_id, token, 'Second request'))
            await asyncio.sleep(0.1)
            with SessionLocal() as db:
                assert not db.query(ChatMessage).filter_by(
                    session_id=session_id, role='user', content='Second request').first(), (
                    'Next message ran while cancelled database write was still active'
                )
        finally:
            release.set()
            tasks = [first] + ([second] if second else [])
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run())
