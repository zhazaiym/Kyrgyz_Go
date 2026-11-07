"""Run a local PostgreSQL/WebSocket smoke load against the Kerben Travel app."""

import argparse
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

MAX_CONNECTIONS = 8
MAX_MESSAGES_PER_USER = 10
MAX_LIVE_USERS = 1
MAX_LIVE_MESSAGES = 1


def validate_profile(users, messages, provider_mode, allow_live=False):
    if not 1 <= users <= MAX_CONNECTIONS:
        raise ValueError(f'users must be between 1 and {MAX_CONNECTIONS}')
    if not 1 <= messages <= MAX_MESSAGES_PER_USER:
        raise ValueError(f'messages must be between 1 and {MAX_MESSAGES_PER_USER}')
    if provider_mode not in {'stub', 'live-gemini'}:
        raise ValueError('provider_mode must be stub or live-gemini')
    if provider_mode == 'live-gemini':
        if not allow_live:
            raise ValueError(
                'live Gemini requires --live-gemini and LOAD_TEST_ALLOW_LIVE_GEMINI=true'
            )
        if users > MAX_LIVE_USERS or messages > MAX_LIVE_MESSAGES:
            raise ValueError('live Gemini is capped at one user and one message')


def validate_database_host(database_url):
    from sqlalchemy.engine import make_url

    url = make_url(database_url)
    if url.get_backend_name() != 'postgresql':
        raise ValueError('load-test database must use PostgreSQL')
    if (url.host or '').casefold() not in {'localhost', '127.0.0.1', '::1'}:
        raise ValueError('load-test database host must be local')


def percentile(values, quantile):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * quantile))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--users', type=int, default=4)
    parser.add_argument('--messages', type=int, default=2)
    parser.add_argument('--live-gemini', action='store_true')
    args = parser.parse_args()
    live_enabled = os.getenv('LOAD_TEST_ALLOW_LIVE_GEMINI', '').casefold() == 'true'
    mode = 'live-gemini' if args.live_gemini else 'stub'
    validate_profile(args.users, args.messages, mode, live_enabled)
    maintenance_url = os.getenv('LOAD_TEST_DATABASE_URL')
    if not maintenance_url:
        raise SystemExit(
            'Set LOAD_TEST_DATABASE_URL to a local PostgreSQL URL with CREATEDB permission'
        )
    try:
        validate_database_host(maintenance_url)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    os.environ['TEST_DATABASE_URL'] = maintenance_url

    from fastapi.testclient import TestClient

    from alembic import command
    from alembic.config import Config
    from tests.postgres_support import temporary_database

    with temporary_database() as isolated_url:
        os.environ['DATABASE_URL'] = isolated_url
        os.environ['SECRET_KEY'] = secrets.token_urlsafe(48)
        os.environ['CORS_ALLOWED_ORIGINS'] = 'http://testserver;http://localhost:3000'
        os.environ['CHAT_ALLOWED_ORIGINS'] = 'http://testserver;http://localhost:3000'
        os.environ['ADMIN_COOKIE_SECURE'] = 'false'
        os.environ['RATE_LIMIT_ENABLED'] = 'false'
        command.upgrade(Config('alembic.ini'), 'head')

        import mysite.translations.jobs as translation_jobs
        from main import app
        from mysite.database.db import engine

        # The load profile measures chat only; startup recovery must never create
        # an unmetered provider call in either stub or explicitly live mode.
        translation_jobs.recover_missing_translations = lambda: 0

        if mode == 'stub':
            import mysite.api.chat_service as chat_service

            async def deterministic_respond(message, state, history, on_chunk=None):
                return 'Local deterministic answer.', dict(state or {}), False

            chat_service.respond = deterministic_respond
        else:
            import threading

            from ML import agent

            if not os.getenv('GEMINI_API_KEY'):
                raise SystemExit('Live mode requires GEMINI_API_KEY in the process environment')
            os.environ['GEMINI_MAX_RETRIES'] = '0'
            call_lock = threading.Lock()
            provider_calls = 0
            measured_call = agent._measured_call

            async def capped_provider_call(operation, invoke, *, timeout):
                nonlocal provider_calls
                if operation in {'extractor', 'generation'}:
                    with call_lock:
                        if provider_calls >= 8:
                            raise RuntimeError('Live Gemini call ceiling (8) reached')
                        provider_calls += 1
                return await measured_call(operation, invoke, timeout=timeout)

            agent._measured_call = capped_provider_call

        latencies = []
        target_errors = []
        generator_errors = []
        started = time.perf_counter()

        def virtual_user(index, client):
            username = f'load_{secrets.token_hex(6)}'
            registered = client.post(
                '/auth/register', json={'username': username, 'password': secrets.token_urlsafe(18)}
            )
            if registered.status_code != 201:
                raise RuntimeError(f'registration returned {registered.status_code}')
            token = registered.json()['access_token']
            created = client.post('/chat/session', headers={'Authorization': f'Bearer {token}'})
            if created.status_code != 200:
                raise RuntimeError(f'session creation returned {created.status_code}')
            sid = created.json()['session_id']
            elapsed = []
            with client.websocket_connect(
                f'/ws/chat/{sid}', headers={'origin': 'http://testserver'}
            ) as websocket:
                websocket.send_json({'type': 'auth', 'token': token})
                if websocket.receive_json().get('type') != 'connected':
                    raise RuntimeError('websocket authentication failed')
                for message_index in range(args.messages):
                    before = time.perf_counter()
                    websocket.send_json(
                        {'type': 'message', 'message': f'load probe {message_index}'}
                    )
                    while True:
                        event = websocket.receive_json()
                        if event.get('type') == 'error':
                            target_errors.append(event.get('code', 'unknown'))
                            break
                        if event.get('type') == 'message_end':
                            elapsed.append(time.perf_counter() - before)
                            break
            history = client.get(
                f'/chat/history/{sid}', headers={'Authorization': f'Bearer {token}'}
            )
            if history.status_code != 200:
                raise RuntimeError(f'PostgreSQL chat history returned {history.status_code}')
            return elapsed

        with TestClient(app, client=('127.0.0.1', 50000)) as client:
            with ThreadPoolExecutor(max_workers=args.users) as executor:
                futures = [
                    executor.submit(virtual_user, index, client) for index in range(args.users)
                ]
                for future in as_completed(futures):
                    try:
                        latencies.extend(future.result())
                    except Exception as exc:
                        generator_errors.append(type(exc).__name__)

        duration = time.perf_counter() - started
        engine.dispose()
        request_count = args.users * args.messages
        report = {
            'scope': 'local isolated PostgreSQL and in-process FastAPI only',
            'provider_mode': mode,
            'users': args.users,
            'messages_per_user': args.messages,
            'completed_messages': len(latencies),
            'requests_per_second': round(len(latencies) / duration, 3) if duration else 0,
            'latency_seconds': {
                'p50': round(percentile(latencies, 0.50), 4),
                'p95': round(percentile(latencies, 0.95), 4),
                'p99': round(percentile(latencies, 0.99), 4),
            },
            'error_rate': round((len(target_errors) + len(generator_errors)) / request_count, 4),
            'websocket_disconnects': sum(
                error == 'WebSocketDisconnect' for error in generator_errors
            ),
            'target_errors': len(target_errors),
            'generator_errors': len(generator_errors),
            'duration_seconds': round(duration, 3),
        }
        print(json.dumps(report, indent=2))
        if target_errors or generator_errors or len(latencies) != request_count:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
