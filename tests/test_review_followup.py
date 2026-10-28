import asyncio
import os
import subprocess
import sys
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from starlette.websockets import WebSocketDisconnect
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from main import app
from mysite.api import chat_service, client_auth, resource_limits
from mysite.database import models as m
from mysite.database.chat_models import ChatClient, ChatMessage, ChatSession
from mysite.database.db import SessionLocal, engine
from mysite.database.selection_models import TravelSelection
from tests.postgres_support import temporary_database
from tests.test_main_regressions import PASSWORD, headers, register
from tests.test_main_regressions import selection as selection
from tests.test_user_flow_regressions import complete, submit


def test_caddy_clients_have_independent_http_quotas_and_https_scheme(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('HTTP_REQUESTS_PER_MINUTE', '1')
    proxy = ProxyHeadersMiddleware(app, trusted_hosts='172.30.240.2')
    with TestClient(proxy, client=('172.30.240.2', 1234)) as browser:
        first = {'X-Forwarded-For': '203.0.113.201', 'X-Forwarded-Proto': 'https'}
        second = {'X-Forwarded-For': '203.0.113.202', 'X-Forwarded-Proto': 'https'}
        response = browser.get('/openapi.json', headers=first)
        assert response.status_code == 200
        assert 'strict-transport-security' in response.headers
        limited = browser.get('/openapi.json', headers=first)
        assert limited.status_code == 429
        assert limited.json()['detail']['code'] == 'rate_limited'
        assert browser.get('/openapi.json', headers=second).status_code == 200


def test_websocket_limit_behind_caddy_is_per_client_not_per_proxy(client):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']
    proxy = ProxyHeadersMiddleware(app, trusted_hosts='172.30.240.2')
    with TestClient(proxy, client=('172.30.240.2', 1234)) as browser, ExitStack() as sockets:
        for address in ['203.0.113.211'] * 8 + ['203.0.113.212']:
            socket = sockets.enter_context(
                browser.websocket_connect(
                    f'/ws/chat/{sid}',
                    headers={'origin': 'http://localhost:3000', 'x-forwarded-for': address},
                )
            )
            socket.send_json({'type': 'auth', 'token': account['access_token']})
            assert socket.receive_json()['type'] == 'connected'
        with pytest.raises(WebSocketDisconnect) as rejected:
            with browser.websocket_connect(
                f'/ws/chat/{sid}',
                headers={'origin': 'http://localhost:3000', 'x-forwarded-for': '203.0.113.211'},
            ):
                pass
        assert rejected.value.code == 1013


def test_http_limiter_health_and_admin_assets_do_not_write_to_postgresql(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('HTTP_REQUESTS_PER_MINUTE', '1')
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', record)
    try:
        with TestClient(app, client=('198.51.100.202', 1)) as browser:
            assert browser.get('/openapi.json').status_code == 200
            assert browser.get('/openapi.json').status_code == 429
            for _ in range(3):
                assert browser.get('/').status_code == 200
                assert browser.get('/admin/statics/css/tabler.min.css').status_code != 429
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert statements == []


def test_http_limiter_bounds_memory_and_expires_old_ip_buckets(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('HTTP_IP_BUCKETS', '2')
    monkeypatch.setattr(resource_limits.time, 'monotonic', lambda: 120)
    limiter = resource_limits.ResourceLimitsMiddleware(app)
    limiter.http_quota('first')
    limiter.http_quota('second')
    limiter.http_quota('third')
    assert 'first' not in limiter.http_counters
    assert len(limiter.http_counters) == 2
    monkeypatch.setattr(resource_limits.time, 'monotonic', lambda: 180)
    limiter.http_quota('third')
    assert len(limiter.http_counters) == 1


@pytest.mark.parametrize(
    'name,value',
    [
        ('MAX_REQUEST_BODY_BYTES', '1MB'),
        ('HTTP_MAX_CONCURRENT', '0'),
        ('AUTH_MAX_CONCURRENT', '999'),
        ('REQUEST_BODY_TIMEOUT', 'abc'),
    ],
)
def test_invalid_resource_settings_fail_during_initialization(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name):
        resource_limits.ResourceLimitsMiddleware(app)


def test_validated_settings_are_not_reparsed_for_each_request(monkeypatch):
    resource_limits.validate_resource_settings()
    original = resource_limits.setting('MAX_REQUEST_BODY_BYTES')
    monkeypatch.setenv('MAX_REQUEST_BODY_BYTES', '1MB')
    assert resource_limits.setting('MAX_REQUEST_BODY_BYTES') == original


@pytest.mark.parametrize('reset_during_verify', [False, True])
def test_login_hash_work_holds_no_row_lock_and_rejects_a_concurrent_reset(
    client, monkeypatch, reset_during_verify
):
    account, email = register(client)
    original_verify = client_auth.passwords.verify
    changed_hash = client_auth.passwords.hash('ChangedPassword123!')

    def verify(password, encoded):
        with SessionLocal() as db:
            row = (
                db.query(ChatClient)
                .filter_by(id=account['client_id'])
                .with_for_update(nowait=True)
                .one()
            )
            if reset_during_verify:
                row.password_hash = changed_hash
            db.commit()
        return original_verify(password, encoded)

    monkeypatch.setattr(client_auth.passwords, 'verify', verify)
    response = client.post('/auth/login', json={'email': email, 'password': PASSWORD})
    assert response.status_code == (401 if reset_during_verify else 200)


@pytest.mark.parametrize('route', ['put', 'patch', 'sqladmin'])
def test_completed_request_cannot_be_reopened_through_any_admin_path(
    client, admin_headers, selection, route
):
    _, request_id = submit(client, selection)
    with SessionLocal() as db:
        db.get(m.TravelRequest, request_id).status = m.RequestStatusChoices.completed
        db.commit()
    if route == 'put':
        response = client.put(
            f'/travel-requests/{request_id}/', headers=admin_headers, json={'status': 'in_progress'}
        )
        assert response.status_code == 409
    elif route == 'patch':
        response = client.patch(
            f'/admin/requests/{request_id}/status/',
            headers=admin_headers,
            json={'status': 'in_progress'},
        )
        assert response.status_code == 409
    else:
        client.post(
            '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
        )
        try:
            response = client.post(
                f'/admin/chat-request/edit/{request_id}',
                data={'status': 'in_progress'},
                headers={'origin': 'http://testserver'},
            )
            assert response.status_code == 400
        finally:
            client.get('/admin/logout')
    with SessionLocal() as db:
        assert db.get(m.TravelRequest, request_id).status == m.RequestStatusChoices.completed


def test_orm_write_cannot_reopen_a_completed_request(client, selection):
    _, request_id = submit(client, selection)
    with SessionLocal() as db:
        row = db.get(m.TravelRequest, request_id)
        row.status = m.RequestStatusChoices.completed
        db.commit()
        row.status = m.RequestStatusChoices.cancelled
        with pytest.raises((ValueError, IntegrityError)):
            db.commit()
        db.rollback()


def test_stale_orm_editor_cannot_overwrite_a_concurrently_completed_request(client, selection):
    _, request_id = submit(client, selection)
    with SessionLocal() as stale:
        row = stale.get(m.TravelRequest, request_id)
        with SessionLocal() as other:
            other.get(m.TravelRequest, request_id).status = m.RequestStatusChoices.completed
            other.commit()
        row.status = m.RequestStatusChoices.in_progress
        with pytest.raises((ValueError, IntegrityError)):
            stale.commit()
        stale.rollback()


def test_one_chat_cannot_be_attached_to_two_selections(client, selection):
    account, identity, _ = selection
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        db.add(TravelSelection(client_id=account['client_id'], session_id=sid))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add_all(
            [
                TravelSelection(client_id=account['client_id']),
                TravelSelection(client_id=account['client_id']),
            ]
        )
        db.commit()


@pytest.mark.parametrize('language', ['ru', 'en', 'ky', 'de', 'zh'])
@pytest.mark.parametrize('reason', ['inactive_tour', 'past_date'])
def test_stale_chat_confirmation_returns_a_saved_human_reply_and_new_preview(
    client, selection, monkeypatch, language, reason
):
    account, identity, services = selection
    tour_id = next(item['id'] for item in services if item['kind'] == 'tour')
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        row = db.get(ChatSession, sid)
        row.state = {**complete(row.state), 'language': language}
        row.stage = 'awaiting_confirmation'
        old_revision = row.revision
        if reason == 'inactive_tour':
            db.get(m.Tour, tour_id).is_active = False
        else:
            row.state = {**row.state, 'travel_date': (date.today() - timedelta(days=1)).isoformat()}
        db.commit()

    async def unexpected_model(*args, **kwargs):
        raise AssertionError('A stale confirmation must be handled by the backend')

    monkeypatch.setattr(chat_service, 'respond', unexpected_model)
    response = asyncio.run(
        chat_service.process_message(
            sid, account['client_id'], account['access_token'], 'I confirm'
        )
    )
    assert response['stage'] == 'collecting'
    assert response['revision'] == old_revision + 1
    assert not response['booking_intent']
    assert not response['booking_preview']['can_confirm']
    assert 'missing_fields' not in response['answer']
    with SessionLocal() as db:
        messages = (
            db.query(ChatMessage)
            .filter_by(session_id=sid)
            .order_by(ChatMessage.id.desc())
            .limit(2)
            .all()
        )
        assert [(row.role, row.content) for row in reversed(messages)] == [
            ('user', 'I confirm'),
            ('assistant', response['answer']),
        ]


def test_compose_trusts_the_fixed_caddy_address_and_example_database_is_docker_reachable():
    compose = Path('docker-compose.yml').read_text(encoding='utf-8')
    assert 'FORWARDED_ALLOW_IPS: ${FORWARDED_ALLOW_IPS:-172.30.240.2}' in compose
    assert 'ipv4_address: ${CADDY_PROXY_IP:-172.30.240.2}' in compose
    active = [
        line
        for line in Path('.env.example').read_text().splitlines()
        if line.startswith('DATABASE_URL=')
    ]
    assert len(active) == 1 and '@host.docker.internal:' in active[0]


def test_unique_session_migration_rejects_legacy_conflicts_without_deleting_data():
    script = """
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from mysite.database.chat_models import ChatClient, ChatSession
from mysite.database.selection_models import TravelSelection

config = Config('alembic.ini')
command.upgrade(config, '20261027_0011')
engine = create_engine(os.environ['DATABASE_URL'])
try:
    with Session(engine) as db:
        client = ChatClient(username='migration_owner', password_hash='unused')
        db.add(client)
        db.flush()
        db.add(ChatSession(id='legacy-duplicate', client_id=client.id, state={}))
        db.flush()
        db.add_all([TravelSelection(client_id=client.id, session_id='legacy-duplicate') for _ in range(2)])
        db.commit()
    try:
        command.upgrade(config, 'head')
    except RuntimeError as exc:
        assert 'Duplicate travel_selections.session_id' in str(exc)
    else:
        raise AssertionError('Conflicting selections must be reviewed before migration')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM travel_selections')) == 2
        assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '20261027_0011'
finally:
    engine.dispose()
"""
    with temporary_database() as url:
        result = subprocess.run(
            [sys.executable, '-c', script],
            env={**os.environ, 'DATABASE_URL': url},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
