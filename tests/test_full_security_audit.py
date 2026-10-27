import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from main import app
from mysite.api import chat_service, rate_limit
from mysite.api.admin import SECRET_KEY, password_hash
from mysite.api.resource_limits import ResourceLimitsMiddleware
from mysite.database import models as m
from mysite.database.chat_models import ChatMessage
from mysite.database.db import SessionLocal, engine
from tests.test_main_regressions import headers, register


@pytest.mark.parametrize(
    'claims,algorithm',
    [
        ({'sub': '1'}, 'HS256'),
        ({'exp': 4_000_000_000}, 'HS256'),
        ({'sub': '1', 'exp': 1}, 'HS256'),
        ({'sub': '1', 'exp': 4_000_000_000}, 'HS384'),
        ({'sub': '1', 'exp': 4_000_000_000}, 'none'),
    ],
)
def test_admin_jwt_rejects_missing_claims_expiration_and_wrong_algorithms(
    client, claims, algorithm
):
    # A longer valid HS384 key avoids a warning unrelated to algorithm rejection.
    key = (
        None
        if algorithm == 'none'
        else (SECRET_KEY + 'padding-for-hs384' if algorithm == 'HS384' else SECRET_KEY)
    )
    token = jwt.encode(claims, key, algorithm=algorithm)
    assert client.get('/admin/me/', headers={'Authorization': 'Bearer ' + token}).status_code == 401


def test_admin_token_is_revoked_by_deactivation(client):
    with SessionLocal() as db:
        admin = m.Admin(
            username='disabled_' + uuid4().hex[:12],
            hashed_password=password_hash.hash('AuditPassword123!'),
        )
        db.add(admin)
        db.commit()
        identity = admin.id
    token = jwt.encode(
        {'sub': str(identity), 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
        SECRET_KEY,
        algorithm='HS256',
    )
    auth = {'Authorization': 'Bearer ' + token}
    assert client.get('/admin/me/', headers=auth).status_code == 200
    with SessionLocal() as db:
        db.get(m.Admin, identity).is_active = False
        db.commit()
    assert client.get('/admin/me/', headers=auth).status_code == 401


@pytest.mark.parametrize(
    'payload',
    ["' OR 1=1;--", "'; DROP TABLE tours;--", '{"$ne":null}', '<script>alert(1)</script>'],
)
def test_injection_payloads_remain_values_and_never_bypass_auth(client, payload):
    assert client.get('/tours/', params={'search': payload}).status_code == 200
    assert client.get('/tours/', params={'order_by': payload}).status_code == 422
    assert (
        client.post(
            '/auth/login', json={'username': payload, 'password': 'WrongPassword123!'}
        ).status_code
        == 401
    )
    with SessionLocal() as db:
        assert db.query(m.Tour).count() >= 0
    response = client.get('/tours/', params={'search': payload})
    assert response.headers['content-type'].startswith('application/json')
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_oversized_and_chunked_requests_are_rejected_before_json_parsing(client, monkeypatch):
    monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', '1024')
    assert client.post('/auth/login', content=b'x' * 1025).status_code == 413

    def chunks():
        yield b'x' * 700
        yield b'x' * 700

    assert client.post('/auth/login', content=chunks()).status_code == 413
    assert (
        client.post('/auth/login', content=b'x' * 1400, headers={'Content-Length': '1'}).status_code
        == 413
    )
    assert (
        client.post('/auth/login', content=b'{}', headers={'Content-Length': 'invalid'}).status_code
        == 400
    )
    assert client.get('/tours/?search=' + 'x' * 9000).status_code == 414


def test_http_quota_cannot_be_bypassed_with_untrusted_forwarded_headers(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('HTTP_REQUESTS_PER_MINUTE', '3')
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: 1_950_000_000)
    with TestClient(app, client=('198.51.100.111', 50001)) as browser:
        statuses = [
            browser.get('/openapi.json', headers={'X-Forwarded-For': f'203.0.113.{n}'}).status_code
            for n in range(4)
        ]
        assert statuses == [200, 200, 200, 429]
        assert int(browser.get('/openapi.json').headers['retry-after']) > 0


def test_blocked_rate_limit_uses_bounded_cache_instead_of_hitting_database(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: 1_950_000_120)
    principal = uuid4().hex
    statements = []

    def count(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO rate_limit_counters'):
            statements.append(statement)

    event.listen(engine, 'before_cursor_execute', count)
    try:
        rate_limit.enforce_rate_limit('audit-cache', principal, max_requests=1, window_seconds=60)
        for _ in range(30):
            with pytest.raises(HTTPException) as rejected:
                rate_limit.enforce_rate_limit(
                    'audit-cache', principal, max_requests=1, window_seconds=60
                )
            assert rejected.value.status_code == 429
    finally:
        event.remove(engine, 'before_cursor_execute', count)
    assert len(statements) == 2
    assert len(rate_limit._blocked) <= 4096


def test_rate_counter_is_atomic_across_concurrent_database_sessions():
    identity = uuid4().hex

    def consume(_):
        return rate_limit.consume_rate_limit(
            'audit-atomic', identity, max_requests=100, window_seconds=60, current_time=120
        )[0]

    with ThreadPoolExecutor(max_workers=8) as workers:
        assert sorted(workers.map(consume, range(16))) == list(range(1, 17))


def test_http_admission_rejects_excess_concurrency_and_releases_capacity(monkeypatch):
    monkeypatch.setenv('HTTP_MAX_CONCURRENT', '2')

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        active = 0

        async def slow(scope, receive, send):
            nonlocal active
            active += 1
            if active == 2:
                entered.set()
            await release.wait()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'OK'})

        middleware = ResourceLimitsMiddleware(slow)

        async def request():
            responses = []

            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}

            async def send(message):
                responses.append(message)

            await middleware(
                {
                    'type': 'http',
                    'method': 'GET',
                    'path': '/',
                    'scheme': 'http',
                    'headers': [],
                    'query_string': b'',
                    'client': ('audit', 1),
                },
                receive,
                send,
            )
            return responses[0]['status']

        first, second = asyncio.create_task(request()), asyncio.create_task(request())
        await asyncio.wait_for(entered.wait(), 2)
        assert await request() == 503
        release.set()
        assert await first == await second == 200
        assert await request() == 200
        assert middleware.http_active == 0

    asyncio.run(scenario())


def test_websocket_size_and_connection_limits(client, monkeypatch):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']
    monkeypatch.setenv('WS_MAX_PER_IP', '1')
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': account['access_token']})
        assert socket.receive_json()['type'] == 'connected'
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as busy:
            with client.websocket_connect(
                f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
            ):
                pass
        assert busy.value.code == 1013
        socket.send_json({'type': 'message', 'message': 'x' * 17000})
        with pytest.raises(WebSocketDisconnect) as large:
            socket.receive_json()
        assert large.value.code == 1009
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': account['access_token']})
        assert socket.receive_json()['type'] == 'connected'


def test_ai_admission_bounds_parallel_calls_and_does_not_leave_orphan_messages(client, monkeypatch):
    account, _ = register(client)
    sessions = [
        client.post('/chat/session', headers=headers(account)).json()['session_id']
        for _ in range(2)
    ]
    monkeypatch.setenv('AI_MAX_CONCURRENT', '1')

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow(message, state, history, on_chunk=None):
            entered.set()
            await release.wait()
            return 'Answer', state, False

        monkeypatch.setattr(chat_service, 'respond', slow)
        first = asyncio.create_task(
            chat_service.process_message(
                sessions[0], account['client_id'], account['access_token'], 'first'
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        try:
            with pytest.raises(HTTPException) as busy:
                await chat_service.process_message(
                    sessions[1], account['client_id'], account['access_token'], 'busy'
                )
            assert busy.value.status_code == 503
            with SessionLocal() as db:
                assert (
                    db.query(ChatMessage).filter_by(session_id=sessions[1], role='user').count()
                    == 0
                )
        finally:
            release.set()
            await first
        assert (
            await chat_service.process_message(
                sessions[1], account['client_id'], account['access_token'], 'retry'
            )
        )['answer'] == 'Answer'

    asyncio.run(scenario())


def test_cookie_admin_actions_reject_cross_site_requests(client):
    response = client.post(
        '/admin/tour/create',
        headers={
            'Cookie': 'session=untrusted',
            'Origin': 'https://evil.example',
            'Sec-Fetch-Site': 'cross-site',
        },
        data={'title': 'CSRF'},
    )
    assert response.status_code == 403


def test_sqladmin_escapes_stored_html_in_catalogue_details(client, admin_headers):
    marker = '<script>window.__stored_xss_marker__=1</script>'
    with SessionLocal() as db:
        row = m.Tour(title='XSS audit', description=marker, price=10)
        db.add(row)
        db.commit()
        identity = row.id
    login = client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    assert login.status_code == 200
    try:
        detail = client.get(f'/admin/tour/details/{identity}')
        assert detail.status_code == 200
        assert marker not in detail.text
        assert '&lt;script&gt;window.__stored_xss_marker__=1&lt;/script&gt;' in detail.text
    finally:
        client.get('/admin/logout')


def test_password_work_has_a_separate_capacity_limit(monkeypatch):
    from mysite.api.password_work import BoundedPasswords, password_capacity

    monkeypatch.setenv('AUTH_MAX_CONCURRENT', '1')
    with password_capacity():
        with pytest.raises(HTTPException) as busy:
            BoundedPasswords().hash('ValidPassword123!')
        assert busy.value.status_code == 503
    hasher = BoundedPasswords()
    encoded = hasher.hash('ValidPassword123!')
    assert hasher.verify('ValidPassword123!', encoded)
    assert not hasher.verify('ValidPassword123!', 'corrupt legacy hash')


@pytest.mark.parametrize('payload', ['{', '[]', '{"type":"message","message":""}'])
def test_repeated_invalid_websocket_frames_are_disconnected(client, payload):
    from starlette.websockets import WebSocketDisconnect

    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': account['access_token']})
        assert socket.receive_json()['type'] == 'connected'
        for _ in range(3):
            socket.send_text(payload)
            assert socket.receive_json()['code'] == 'invalid_message'
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008


def test_headers_are_bounded_before_authentication(client):
    assert client.get('/', headers={'X-Audit': 'x' * 33000}).status_code == 431


def test_reset_email_is_sent_after_the_generic_response(client, monkeypatch):
    from mysite.api import password_reset

    account, email = register(client)
    response_body_seen = []

    def mail(address, token):
        assert response_body_seen, 'SMTP must not delay the generic HTTP response'
        assert address == email

    monkeypatch.setattr(password_reset, 'send_reset_email', mail)
    payload = ('{"email":"' + email + '"}').encode()

    async def scenario():
        async def receive():
            return {'type': 'http.request', 'body': payload, 'more_body': False}

        async def send(message):
            if message['type'] == 'http.response.body':
                response_body_seen.append(message['body'])

        await app(
            {
                'type': 'http',
                'asgi': {'version': '3.0'},
                'method': 'POST',
                'path': '/account/forgot-password',
                'raw_path': b'/account/forgot-password',
                'root_path': '',
                'scheme': 'http',
                'query_string': b'',
                'server': ('testserver', 80),
                'client': ('reset-audit', 1),
                'headers': [(b'content-type', b'application/json'), (b'host', b'testserver')],
            },
            receive,
            send,
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    'answer,state,intent',
    [
        ('', {}, False),
        ('Answer', None, False),
        ('Answer', {}, 'false'),
        ('Answer', {'notes': 'x' * 33000}, False),
        ('Answer', {'people_count': float('nan')}, False),
    ],
)
def test_backend_rejects_invalid_ai_contract_without_modifying_agent(
    client, monkeypatch, answer, state, intent
):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']

    async def invalid(*args, **kwargs):
        return answer, state, intent

    monkeypatch.setattr(chat_service, 'respond', invalid)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            chat_service.process_message(
                sid, account['client_id'], account['access_token'], 'Question'
            )
        )
    assert rejected.value.status_code == 502
    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=sid, role='user').count() == 0


@pytest.mark.parametrize('error', [RuntimeError('Model unavailable'), asyncio.CancelledError()])
def test_model_failure_or_cancellation_does_not_leave_pending_messages(client, monkeypatch, error):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']

    async def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(chat_service, 'respond', fail)
    with pytest.raises(type(error)):
        asyncio.run(
            chat_service.process_message(
                sid, account['client_id'], account['access_token'], 'Failed question'
            )
        )
    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=sid, role='user').count() == 0
    assert sid not in chat_service._locks


def test_failure_cleanup_preserves_a_reply_already_saved_by_the_database_worker(
    client, monkeypatch
):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']

    async def answer(*args, **kwargs):
        return 'Saved answer', {}, False

    monkeypatch.setattr(chat_service, 'respond', answer)
    asyncio.run(
        chat_service.process_message(sid, account['client_id'], account['access_token'], 'Question')
    )
    with SessionLocal() as db:
        message_id = db.query(ChatMessage).filter_by(session_id=sid, role='user').one().id
    chat_service._discard_failed_message(sid, message_id)
    with SessionLocal() as db:
        messages = db.query(ChatMessage).filter_by(session_id=sid).order_by(ChatMessage.id).all()
        assert [(message.role, message.content) for message in messages][-2:] == [
            ('user', 'Question'),
            ('assistant', 'Saved answer'),
        ]
