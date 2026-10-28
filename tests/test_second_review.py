import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from main import app
from mysite.api import chat_ws, client_auth, password_reset, rate_limit, resource_limits
from mysite.api.token_maintenance import cleanup_expired_tokens
from mysite.database import models as m
from mysite.database.chat_models import ChatClient, ChatLoginToken, ChatSession
from mysite.database.db import SessionLocal, engine
from mysite.database.password_reset_models import PasswordResetToken
from scripts import ci_deploy
from tests.test_main_regressions import PASSWORD, headers, register
from tests.test_main_regressions import selection as selection
from tests.test_user_flow_regressions import complete, submit


@pytest.mark.skipif(shutil.which('docker') is None, reason='Docker Compose CLI unavailable')
def test_rendered_compose_reserves_separate_api_and_caddy_addresses(tmp_path):
    shutil.copy2('docker-compose.yml', tmp_path / 'docker-compose.yml')
    shutil.copy2('.env.example', tmp_path / '.env')
    env = {
        **os.environ,
        'API_PROXY_IP': '172.30.240.3',
        'CADDY_PROXY_IP': '172.30.240.2',
        'PROXY_SUBNET': '172.30.240.0/28',
    }
    result = subprocess.run(
        ['docker', 'compose', '--profile', 'https', 'config', '--format', 'json'],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)['services']
    assert services['api']['networks']['proxy']['ipv4_address'] == '172.30.240.3'
    assert services['https']['networks']['proxy']['ipv4_address'] == '172.30.240.2'


def test_dockerfile_is_shipped_and_legacy_digest_probe_handles_missing_file(monkeypatch, tmp_path):
    assert 'Dockerfile main.py' in Path('Dockerfile').read_text()

    def output(arguments):
        code = arguments[-1].replace('/app/Dockerfile', (tmp_path / 'Dockerfile').as_posix())
        return subprocess.check_output([sys.executable, '-c', code], text=True).strip()

    monkeypatch.setattr(ci_deploy, 'output', output)
    assert ci_deploy.deployed_runtime_digest(
        'old', 'Dockerfile'
    ) == ci_deploy.dockerfile_runtime_digest(b'')
    source = b'FROM python:3.12-slim\nCMD ["python", "main.py"]\n'
    (tmp_path / 'Dockerfile').write_bytes(source)
    assert ci_deploy.deployed_runtime_digest(
        'new', 'Dockerfile'
    ) == ci_deploy.dockerfile_runtime_digest(source)


def test_pr_cannot_share_the_production_deployment_concurrency_group():
    workflow = Path('.github/workflows/deploy.yml').read_text()
    assert 'concurrency:' not in workflow.split('jobs:', 1)[0]
    assert 'concurrency:' not in workflow.split('  deploy:', 1)[0]
    assert '      group: kyrgyzgo-production' in workflow.split('  deploy:', 1)[1]


def test_schema_changing_image_cannot_be_automatically_activated():
    with pytest.raises(RuntimeError, match='maintenance migration'):
        ci_deploy.require_same_schema(['old'], ['new'])
    ci_deploy.require_same_schema(['same'], ['same'])


@pytest.mark.parametrize('schema_changed', [False, True])
def test_deployment_failure_never_activates_a_new_schema_and_restores_exact_override(
    monkeypatch, tmp_path, schema_changed
):
    root, releases, backups = (tmp_path / name for name in ('root', 'releases', 'backups'))
    for path in (root, releases, backups):
        path.mkdir()
    override = tmp_path / 'override.yml'
    previous = 'services:\n  api:\n    image: old\n    environment:\n      KEEP: original\n'
    override.write_text(previous)
    for name in ('docker-compose.yml', 'Caddyfile', '.env'):
        (root / name).write_text('test fixture')
    for name, value in [
        ('ROOT', root),
        ('RELEASES', releases),
        ('BACKUPS', backups),
        ('OVERRIDE', override),
        ('DEPLOY_LOCK', tmp_path / 'lock'),
    ]:
        monkeypatch.setattr(ci_deploy, name, value)
    monkeypatch.setitem(sys.modules, 'fcntl', SimpleNamespace(LOCK_EX=1, flock=lambda *args: None))
    monkeypatch.setattr(ci_deploy.os, 'umask', lambda mode: 0)
    monkeypatch.setattr(
        ci_deploy.shutil, 'disk_usage', lambda path: SimpleNamespace(free=10 * 1024**3)
    )
    monkeypatch.setattr(
        ci_deploy, 'compose_output', lambda *args: 'old-container' if args[0] == 'ps' else ''
    )
    monkeypatch.setattr(
        ci_deploy,
        'output',
        lambda args: json.dumps(
            [
                {
                    'State': {'Health': {'Status': 'healthy'}},
                    'Image': 'old-image-id',
                    'Config': {'Image': 'old'},
                }
            ]
        ),
    )
    monkeypatch.setattr(ci_deploy, 'deployed_runtime_digest', lambda *args: 'legacy-missing')
    monkeypatch.setattr(ci_deploy, 'deployed_schema', lambda container: ['old'])
    monkeypatch.setattr(
        ci_deploy, 'candidate_schema', lambda image: ['new' if schema_changed else 'old']
    )

    def run(args, **kwargs):
        if 'pg_dump' in ' '.join(args):
            kwargs['stdout'].write(b'PGDMPfixture')

    monkeypatch.setattr(ci_deploy, 'run', run)
    activated = []

    def compose(*args):
        if args[0] == 'up':
            activated.append(override.read_text())
            if len(activated) == 1:
                raise RuntimeError('Candidate health failure')

    monkeypatch.setattr(ci_deploy, 'compose', compose)
    source = io.BytesIO()
    with tarfile.open(fileobj=source, mode='w:gz') as archive:
        for name in ci_deploy.ALLOWED_FILES:
            data = (
                b'FROM python:3.12-slim\nCMD ["python", "main.py"]\n'
                if name == 'Dockerfile'
                else b'fixture'
            )
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    source.seek(0)
    with pytest.raises(RuntimeError):
        ci_deploy.deploy('a' * 40, source)
    assert override.read_text() == previous
    state = json.loads(next(backups.glob('*/deployment-state.json')).read_text())
    if schema_changed:
        assert activated == [] and state['status'] == 'migration_required'
    else:
        assert len(activated) == 2 and activated[-1] == previous
        assert state['status'] == 'rolled_back'


def test_ipv6_rotation_shares_a_prefix_quota_without_exhausting_global_capacity(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('HTTP_IP_BUCKETS', '2')
    monkeypatch.setenv('HTTP_REQUESTS_PER_MINUTE', '2')
    limiter = resource_limits.ResourceLimitsMiddleware(None)
    limiter.http_quota('2001:db8:1::1')
    limiter.http_quota('2001:db8:1::2')
    with pytest.raises(HTTPException) as limited:
        limiter.http_quota('2001:db8:1::3')
    assert limited.value.status_code == 429
    for number in range(1, 100):
        limiter.http_quota(f'198.51.100.{number}')
    limiter.http_quota('203.0.113.210')
    assert len(limiter.http_counters) == 2


@pytest.mark.parametrize('kind', ['hotel', 'transport'])
def test_button_confirmation_recovers_and_an_unavailable_optional_service_can_be_removed(
    client, selection, kind
):
    account, identity, services = selection
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        row = db.get(ChatSession, sid)
        row.state = complete(row.state)
        row.stage = 'collecting'
        identity = next(item['id'] for item in services if item['kind'] == kind)
        db.commit()
    collecting_preview = client.post(
        '/booking/preview', headers=headers(account), json={'session_id': sid}
    )
    assert collecting_preview.status_code == 200
    assert not collecting_preview.json()['can_confirm']
    with SessionLocal() as db:
        row = db.get(ChatSession, sid)
        row.stage = 'awaiting_confirmation'
        db.get(m.Hotel if kind == 'hotel' else m.Transport, identity).is_active = False
        db.commit()
    response = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': 0, 'confirmed': True},
    )
    assert response.status_code == 409
    data = response.json()['detail']
    assert data['stage'] == 'collecting' and data['revision'] == 1
    assert data['code'] == 'booking_needs_update'
    removed = client.delete(f'/chat/{sid}/services/{kind}', headers=headers(account))
    assert removed.status_code == 200
    assert f'valid_{kind}' not in removed.json()['booking_preview']['missing_fields']
    assert removed.json()['stage'] == 'awaiting_confirmation'
    assert removed.json()['booking_preview']['can_confirm']
    from mysite.api.booking_text import booking_text

    assert (
        removed.json()['answer']
        != booking_text(removed.json()['booking_preview']['data'])['service_removed']
    )
    with SessionLocal() as db:
        assert f'{kind}_id' not in db.get(ChatSession, sid).state
    stranger, _ = register(client)
    assert (
        client.delete(f'/chat/{sid}/services/{kind}', headers=headers(stranger)).status_code == 404
    )
    confirmed = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': removed.json()['revision'], 'confirmed': True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()['status'] == 'submitted'


def test_password_reset_hashing_does_not_lock_the_client_row(client, monkeypatch):
    account, email = register(client)
    sent = []
    monkeypatch.setattr(password_reset, 'send_reset_email', lambda email, token: sent.append(token))
    client.post('/account/forgot-password', json={'email': email})
    original = password_reset.passwords.hash

    def encode(password):
        with SessionLocal() as db:
            db.query(ChatClient).filter_by(id=account['client_id']).with_for_update(
                nowait=True
            ).one()
        return original(password)

    monkeypatch.setattr(password_reset.passwords, 'hash', encode)
    assert (
        client.post(
            '/account/reset-password',
            json={'token': sent[0], 'new_password': 'UpdatedPassword123!'},
        ).status_code
        == 200
    )


@pytest.mark.parametrize('phase', ['handshake', 'message'])
def test_websocket_limiter_database_errors_are_reported_without_leaking_details(
    client, monkeypatch, phase
):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']

    def fail(*args, **kwargs):
        raise SQLAlchemyError('private-database-details')

    monkeypatch.setattr(
        chat_ws,
        'enforce_rate_limit' if phase == 'handshake' else 'enforce_chat_message_limits',
        fail,
    )
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        if phase == 'message':
            socket.send_json({'type': 'auth', 'token': account['access_token']})
            assert socket.receive_json()['type'] == 'connected'
            socket.send_json({'type': 'message', 'message': 'Hello'})
        response = socket.receive_json()
        assert response['code'] == 'service_unavailable'
        assert 'private-database-details' not in response['message']


def test_binary_websocket_frame_is_a_controlled_validation_error(client):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': account['access_token']})
        assert socket.receive_json()['type'] == 'connected'
        socket.send_bytes(b'not a text frame')
        assert socket.receive_json()['code'] == 'invalid_message'


def test_client_login_limit_blocks_an_attacking_ip_but_not_another_ip(client, monkeypatch):
    account, email = register(client)
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    identity = {'email': email}
    route = '/auth/login'
    attempts = 8
    with (
        TestClient(app, client=('198.51.100.130', 1)) as attacker,
        TestClient(app, client=('198.51.100.131', 1)) as owner,
    ):
        password = PASSWORD
        assert owner.post(route, json={**identity, 'password': password}).status_code == 200
        for _ in range(attempts):
            assert (
                attacker.post(route, json={**identity, 'password': 'incorrect'}).status_code == 401
            )
        assert attacker.post(route, json={**identity, 'password': password}).status_code == 429
        assert owner.post(route, json={**identity, 'password': password}).status_code == 200


def test_account_limits_use_one_insert_and_one_commit_for_both_counters(monkeypatch):
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    statements, commits = [], []

    def sql(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO rate_limit_counters'):
            statements.append(statement)

    def commit(connection):
        commits.append(True)

    event.listen(engine, 'before_cursor_execute', sql)
    event.listen(engine, 'commit', commit)
    try:
        request = Request({'type': 'http', 'client': ('203.0.113.211', 1), 'headers': []})
        rate_limit.enforce_request_limits(
            'batch-' + uuid4().hex + '-login',
            request,
            'test',
            ip_limit=10,
            identity_limit=5,
            window_seconds=60,
        )
    finally:
        event.remove(engine, 'before_cursor_execute', sql)
        event.remove(engine, 'commit', commit)
    assert len(statements) == 1 and len(commits) == 1


def test_expiry_cleanup_preserves_active_tokens(client):
    account, _ = register(client)
    old = datetime.now(timezone.utc) - timedelta(days=2)
    future = datetime.now(timezone.utc) + timedelta(days=2)
    with SessionLocal() as db:
        expired = ChatLoginToken(
            client_id=account['client_id'], token_hash=uuid4().hex, expires_at=old
        )
        active = PasswordResetToken(
            client_id=account['client_id'], token_hash=uuid4().hex, expires_at=future
        )
        db.add_all([expired, active])
        db.commit()
        expired_id, active_id = expired.id, active.id
    cleanup_expired_tokens()
    with SessionLocal() as db:
        assert db.get(ChatLoginToken, expired_id) is None
        assert db.get(PasswordResetToken, active_id) is not None


def test_failed_authentication_does_not_rollback_the_callers_pending_changes(client):
    account, email = register(client)
    with SessionLocal() as db:
        pending = m.About(title='Pending caller change')
        db.add(pending)
        with pytest.raises(HTTPException):
            client_auth.authenticate_client(
                db,
                email,
                'incorrect',
                email_only=True,
                request=Request(
                    {
                        'type': 'http',
                        'http_version': '1.1',
                        'method': 'POST',
                        'scheme': 'http',
                        'path': '/auth/login',
                        'headers': [],
                        'client': ('198.51.100.14', 54321),
                        'server': ('testserver', 80),
                    }
                ),
            )
        assert pending in db.new


def test_sqladmin_rejects_unsafe_image_urls(client, admin_headers):
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    try:
        response = client.post(
            '/admin/about/create',
            data={
                'title': 'Unsafe image test',
                'description': 'Text',
                'image': 'javascript:alert(1)',
                'is_active': 'y',
            },
        )
        assert response.status_code == 400
        with SessionLocal() as db:
            assert db.query(m.About).filter_by(title='Unsafe image test').count() == 0
    finally:
        client.get('/admin/logout')


def test_bulk_updates_cannot_reopen_a_completed_request(client, selection):
    _, request_id = submit(client, selection)
    with SessionLocal() as db:
        db.get(m.TravelRequest, request_id).status = m.RequestStatusChoices.completed
        db.commit()
        with pytest.raises(IntegrityError):
            db.query(m.TravelRequest).filter_by(id=request_id).update(
                {'status': m.RequestStatusChoices.cancelled}
            )
            db.commit()
        db.rollback()


def test_country_used_only_by_tours_cannot_be_deleted(client, admin_headers):
    with SessionLocal() as db:
        country = m.Country(name='Protected country ' + uuid4().hex)
        db.add(country)
        db.flush()
        identity = country.id
        db.add(m.Tour(title='Country dependency', price=10, country_id=identity))
        db.commit()
    assert client.delete(f'/countries/{identity}/', headers=admin_headers).status_code == 409


def test_demo_tours_cannot_be_selected(client):
    account, _ = register(client)
    with SessionLocal() as db:
        tour = m.Tour(title='ТЕСТ: Demo product', price=10)
        db.add(tour)
        db.commit()
        identity = tour.id
    assert (
        client.post(
            '/travel-selections/', headers=headers(account), json={'tour_id': identity}
        ).status_code
        == 404
    )


def test_short_admin_password_is_rejected_before_database_access(monkeypatch):
    import create_admin

    monkeypatch.setattr('builtins.input', lambda prompt: 'new-admin')
    monkeypatch.setattr(create_admin, 'getpass', lambda prompt: 'short')

    def unexpected():
        raise AssertionError('A weak password must not reach the database')

    monkeypatch.setattr(create_admin, 'SessionLocal', unexpected)
    create_admin.create_admin()


def test_catalogue_translation_runs_after_commit_without_a_pooled_connection(
    client, admin_headers, monkeypatch
):
    observations = []

    def translate(source):
        observations.append(engine.pool.checkedout())
        with SessionLocal() as db:
            assert db.query(m.FAQ).filter_by(question='Committed before network').count() == 1
        return {lang: source for lang in ('en', 'de', 'zh')}

    monkeypatch.setattr('mysite.translations.content.translate_fields', translate)
    response = client.post(
        '/faqs/',
        headers=admin_headers,
        json={'question': 'Committed before network', 'answer': 'Answer'},
    )
    assert response.status_code == 200
    assert observations == [0]


def test_null_completed_status_is_rejected_by_schema_before_route_logic(
    client, admin_headers, selection
):
    _, request_id = submit(client, selection)
    with SessionLocal() as db:
        db.get(m.TravelRequest, request_id).status = m.RequestStatusChoices.completed
        db.commit()
    response = client.put(
        f'/travel-requests/{request_id}/', headers=admin_headers, json={'status': None}
    )
    assert response.status_code == 422


def test_agent_import_preserves_process_proxy_configuration():
    code = """
import os
import mysite.chain.agent
for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
    assert os.environ[key] == 'http://127.0.0.1:9', key
"""
    proxies = {
        key: 'http://127.0.0.1:9'
        for key in (
            'HTTP_PROXY',
            'HTTPS_PROXY',
            'ALL_PROXY',
            'http_proxy',
            'https_proxy',
            'all_proxy',
        )
    }
    result = subprocess.run(
        [sys.executable, '-c', code],
        env={**os.environ, **proxies},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
