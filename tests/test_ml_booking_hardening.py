import asyncio
import json
import threading

import pytest

from mysite.api import chat_service, chat_ws
from mysite.database.chat_models import ChatMessage
from mysite.database.db import SessionLocal
from tests.test_chat_auth import bearer, register


def account_session(client, username):
    token = register(client, username)
    identity = client.get('/auth/me', headers=bearer(token)).json()['client_id']
    sid = client.post('/chat/session', headers=bearer(token)).json()['session_id']
    return token, identity, sid


@pytest.mark.parametrize('same_text', [False, True])
@pytest.mark.parametrize('loser_outcome', ['failure', 'stale_save'])
def test_failed_worker_cleanup_does_not_keep_a_turn_answered_by_another_worker(
    client, same_text, loser_outcome
):
    from fastapi import HTTPException

    token, identity, sid = account_session(client, f'ml_parallel_{same_text}_{loser_outcome}')
    first = chat_service._prepare_message(sid, identity, token, 'Failed first question')
    winning_question = 'Failed first question' if same_text else 'Successful second question'
    second = chat_service._prepare_message(sid, identity, token, winning_question)
    chat_service._save_message_response(
        sid, identity, token, second[3], second[4], 'Answer to second', {}, {}, False
    )
    if loser_outcome == 'failure':
        chat_service._discard_failed_message(sid, first[4])
    else:
        with pytest.raises(HTTPException) as conflict:
            chat_service._save_message_response(
                sid, identity, token, first[3], first[4], 'Stale answer', {}, {}, False
            )
        assert conflict.value.status_code == 409
    with SessionLocal() as db:
        messages = db.query(ChatMessage).filter_by(session_id=sid).order_by(ChatMessage.id).all()
        contents = [row.content for row in messages]
    assert contents[-2:] == [winning_question, 'Answer to second']
    assert len(contents) == 3  # welcome + the winning user/assistant pair


def test_disconnect_cancels_generation_and_cleans_pending_turn(client, monkeypatch):
    token, identity, sid = account_session(client, 'ml_disconnect')

    async def scenario():
        entered = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked(*args, **kwargs):
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        monkeypatch.setattr(chat_service, 'respond', blocked)

        class Socket:
            headers = {'origin': 'http://localhost:3000'}
            client = None

            def __init__(self):
                self.frames = iter(
                    [
                        {'type': 'auth', 'token': token},
                        {'type': 'message', 'message': 'Question before disconnect'},
                    ]
                )

            async def accept(self):
                pass

            async def receive(self):
                frame = next(self.frames, None)
                if frame is not None:
                    return {'type': 'websocket.receive', 'text': json.dumps(frame)}
                await entered.wait()
                return {'type': 'websocket.disconnect', 'code': 1000}

            async def send_json(self, data):
                pass

            async def close(self, code):
                pass

        task = asyncio.create_task(chat_ws.socket(Socket(), sid))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            await asyncio.wait_for(asyncio.shield(task), timeout=2)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert cancelled.is_set()
        assert sid not in chat_service._locks

    asyncio.run(scenario())
    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=sid, role='user').count() == 0


@pytest.mark.parametrize('status', [429, 503, 504])
def test_provider_error_over_websocket_is_safe_and_allows_next_message(client, monkeypatch, status):
    from google.genai.errors import APIError

    from ML.errors import classify_error

    token, _, sid = account_session(client, f'ml_ws_error_{status}')
    calls = 0

    async def reply(message, state, history, on_chunk=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise classify_error(APIError(status, {'error': {'message': 'secret-provider-text'}}))
        return 'Recovered response', state, False

    monkeypatch.setattr(chat_service, 'respond', reply)
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'connected'
        socket.send_json({'type': 'message', 'message': 'First'})
        frames = []
        while True:
            frame = socket.receive_json()
            frames.append(frame)
            if frame == {'type': 'typing', 'status': False}:
                break
        errors = [frame for frame in frames if frame['type'] == 'error']
        assert len(errors) == 1
        assert (
            errors[0]['code']
            == {429: 'ai_rate_limit', 503: 'ai_unavailable', 504: 'ai_timeout'}[status]
        )
        assert 'secret-provider-text' not in json.dumps(frames)
        socket.send_json({'type': 'message', 'message': 'Second'})
        frames = []
        while True:
            frame = socket.receive_json()
            frames.append(frame)
            if frame == {'type': 'typing', 'status': False}:
                break
        assert any(frame['type'] == 'message_end' for frame in frames)
    with SessionLocal() as db:
        assert [
            row.content
            for row in db.query(ChatMessage).filter_by(session_id=sid, role='user').all()
        ] == ['Second']


def test_reply_identity_migration_preserves_old_history_and_downgrades():
    import os
    import subprocess
    import sys

    from sqlalchemy import create_engine, inspect, text

    from tests.postgres_support import temporary_database

    with temporary_database() as url:

        def migrate(revision, direction='upgrade'):
            result = subprocess.run(
                [sys.executable, '-B', '-m', 'alembic', direction, revision],
                env={**os.environ, 'DATABASE_URL': url},
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stderr

        migrate('20261028_0016')
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                identity = connection.execute(
                    text(
                        "INSERT INTO chat_clients(username,password_hash,created_at) VALUES ('legacy_reply','not-a-real-password',now()) RETURNING id"
                    )
                ).scalar_one()
                connection.execute(
                    text(
                        "INSERT INTO chat_sessions(id,client_id,state,revision,message_version,stage,created_at) VALUES ('legacy-session',:identity,'{}',0,0,'consultation',now())"
                    ),
                    {'identity': identity},
                )
                connection.execute(
                    text(
                        "INSERT INTO chat_messages(session_id,role,content,created_at) VALUES ('legacy-session','user','Preserve this history',now())"
                    )
                )
            migrate('head')
            with engine.connect() as connection:
                assert connection.execute(
                    text('SELECT content, reply_to_message_id FROM chat_messages')
                ).one() == ('Preserve this history', None)
            migrate('20261028_0016', 'downgrade')
            assert 'reply_to_message_id' not in {
                column['name'] for column in inspect(engine).get_columns('chat_messages')
            }
            with engine.connect() as connection:
                assert (
                    connection.execute(text('SELECT content FROM chat_messages')).scalar_one()
                    == 'Preserve this history'
                )
        finally:
            engine.dispose()


def test_cancellation_after_prepare_commit_removes_only_its_pending_message(client, monkeypatch):
    token, identity, sid = account_session(client, 'ml_cancel_prepare')
    committed = threading.Event()
    release = threading.Event()
    original_prepare = chat_service._prepare_message

    def paused_prepare(*args):
        result = original_prepare(*args)
        committed.set()
        assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(chat_service, '_prepare_message', paused_prepare)

    async def scenario():
        task = asyncio.create_task(
            chat_service.process_message(sid, identity, token, 'Cancelled preparation')
        )
        try:
            assert await asyncio.to_thread(committed.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=sid, role='user').count() == 0
    assert sid not in chat_service._locks
