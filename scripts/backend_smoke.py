"""HTTP smoke on a disposable PostgreSQL database; optional single live AI call."""

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from tests.postgres_support import temporary_database

ROOT = Path(__file__).resolve().parents[1]


def serve(port):
    import uvicorn

    import mysite.translations.jobs as jobs

    # Do not start background provider calls during the one-call smoke test.
    jobs.recover_missing_translations = lambda: 0
    uvicorn.run('main:app', host='127.0.0.1', port=port, log_level='warning', access_log=False)


def smoke(live_ai=False):
    with temporary_database() as database_url, tempfile.TemporaryDirectory() as media:
        env = dict(os.environ)
        env.update(
            DATABASE_URL=database_url,
            PYTHON_DOTENV_DISABLED='1',
            SECRET_KEY=secrets.token_urlsafe(48),
            MEDIA_ROOT=media,
            SERVE_MEDIA_LOCALLY='true',
            RATE_LIMIT_ENABLED='true',
            ADMIN_COOKIE_SECURE='false',
            CORS_ALLOWED_ORIGINS='https://smoke.example',
            GEMINI_MAX_RETRIES='0',
            CHAT_MAX_OUTPUT_TOKENS='512',
            METRICS_BEARER_TOKEN='',
        )
        with tempfile.TemporaryFile() as logs:
            migration = subprocess.run(
                [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                cwd=ROOT,
                env=env,
                stdout=logs,
                stderr=logs,
                check=False,
            )
            if migration.returncode:
                raise RuntimeError('Migration of empty isolated database failed (logs withheld)')
            print('Empty PostgreSQL: alembic upgrade head OK')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            process = subprocess.Popen(
                [sys.executable, '-m', 'scripts.backend_smoke', '--serve', str(port)],
                cwd=ROOT,
                env=env,
                stdout=logs,
                stderr=logs,
            )
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=55) as http:
                    for _ in range(100):
                        try:
                            if http.get('/').status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.poll() is not None:
                            raise RuntimeError('Uvicorn exited before startup (logs withheld)')
                        time.sleep(0.2)
                    else:
                        raise RuntimeError('Uvicorn startup deadline exceeded')
                    print('Uvicorn TCP startup OK')
                    key_values = [
                        env.get(name, '')
                        for name in (
                            'GEMINI_API_KEY',
                            'GOOGLE_API_KEY',
                            'OPENAI_API_KEY',
                            'ANTHROPIC_API_KEY',
                        )
                        if env.get(name)
                    ]

                    def check(method, path, expected, **kwargs):
                        response = http.request(method, path, **kwargs)
                        assert response.status_code == expected, (
                            f'{method} {path}: {response.status_code}, expected {expected}'
                        )
                        assert not any(key in response.text for key in key_values), (
                            'Secret in HTTP response'
                        )
                        print(f'{method} {path}: {response.status_code}')
                        return response

                    for path in (
                        '/',
                        '/openapi.json',
                        '/tours/',
                        '/hotels/',
                        '/transports/',
                        '/tour-videos/',
                        '/tour-images/',
                        '/contacts/',
                        '/faqs/',
                    ):
                        check('GET', path, 200)
                    for method, path in (
                        ('POST', '/chat/session'),
                        ('GET', '/chat/sessions'),
                        ('POST', '/booking/preview'),
                        ('POST', '/booking/confirm'),
                        ('POST', '/travel-requests/'),
                        ('POST', '/tours/'),
                        ('POST', '/tours/1/reviews/'),
                        ('POST', '/admin/media/'),
                        ('POST', '/admin/media/videos/'),
                        ('GET', '/admin/me/'),
                    ):
                        check(method, path, 401, json={})
                    check('POST', '/api/ask-ai', 422, json={'context': {}})
                    for origin, expected in (
                        ('https://smoke.example', 200),
                        ('https://untrusted.example', 400),
                    ):
                        response = check(
                            'OPTIONS',
                            '/api/ask-ai',
                            expected,
                            headers={
                                'Origin': origin,
                                'Access-Control-Request-Method': 'POST',
                                'Access-Control-Request-Headers': 'Content-Type',
                            },
                        )
                        if expected == 200:
                            assert response.headers['access-control-allow-origin'] == origin
                    if live_ai:
                        response = http.post(
                            '/api/ask-ai',
                            json={
                                'context': {
                                    'destination': 'Кыргызстан',
                                    'notes': 'Одна короткая рекомендация для поездки.',
                                }
                            },
                        )
                        assert not any(key in response.text for key in key_values), (
                            'Secret in AI response'
                        )
                        print(f'Live Gemini via guest HTTP: {response.status_code}')
                        if response.status_code == 200:
                            assert (
                                isinstance(response.json()['answer'], str)
                                and response.json()['answer'].strip()
                            )
                            print('Live Gemini answer: nonempty (content withheld)')
                        else:
                            raise RuntimeError(
                                f'Live Gemini failed safely: HTTP {response.status_code}'
                            )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                logs.seek(0)
                output = logs.read()
                keys = [
                    env.get(name, '')
                    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY')
                    if env.get(name)
                ]
                assert not any(key.encode() in output for key in keys), 'Secret in server logs'
                print('Server logs: no configured AI key values found')
    print('Temporary PostgreSQL database and media removed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live-ai', action='store_true')
    parser.add_argument('--serve', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
    else:
        smoke(args.live_ai)


if __name__ == '__main__':
    main()
