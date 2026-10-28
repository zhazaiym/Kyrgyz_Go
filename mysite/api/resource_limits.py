"""Bounded admission, request sizes and cheap rejection before application work."""

import asyncio
import os
import time
from collections import OrderedDict
from contextlib import contextmanager
from functools import lru_cache
from threading import Lock

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from mysite.api.network_identity import client_network

RESOURCE_LIMITS = {
    'AI_MAX_CONCURRENT': (4, 32),
    'AUTH_MAX_CONCURRENT': (4, 16),
    'HTTP_MAX_CONCURRENT': (64, 512),
    'HTTP_REQUESTS_PER_MINUTE': (120, 100_000),
    'HTTP_IP_BUCKETS': (8192, 65_536),
    'MAX_REQUEST_BODY_BYTES': (1_048_576, 16_777_216),
    'REQUEST_BODY_TIMEOUT': (10, 60),
    'WS_MAX_CONNECTIONS': (64, 512),
    'WS_MAX_PER_IP': (8, 64),
}


@lru_cache(maxsize=len(RESOURCE_LIMITS))
def setting(name):
    default, maximum = RESOURCE_LIMITS[name]
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f'{name} must be an integer') from exc
    if not 1 <= value <= maximum:
        raise RuntimeError(f'{name} must be between 1 and {maximum}')
    return value


@lru_cache(maxsize=1)
def validate_resource_settings():
    for name in RESOURCE_LIMITS:
        setting(name)


_ai_lock = Lock()
_ai_active = 0


@contextmanager
def ai_capacity():
    global _ai_active
    with _ai_lock:
        if _ai_active >= setting('AI_MAX_CONCURRENT'):
            raise HTTPException(503, 'AI is busy; retry shortly', headers={'Retry-After': '5'})
        _ai_active += 1
    try:
        yield
    finally:
        with _ai_lock:
            _ai_active -= 1


class ResourceLimitsMiddleware:
    def __init__(self, app):
        validate_resource_settings()
        self.app = app
        self.lock = Lock()
        self.http_active = 0
        self.ws_active = 0
        self.ws_clients = {}
        self.http_counters = OrderedDict()

    def http_quota(self, address):
        if os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() in {'0', 'false', 'no'}:
            return
        address = client_network(address)
        instant = time.monotonic()
        window = int(instant // 60)
        with self.lock:
            while self.http_counters:
                first = next(iter(self.http_counters))
                if self.http_counters[first][0] == window:
                    break
                self.http_counters.popitem(last=False)
            if address not in self.http_counters:
                if len(self.http_counters) >= setting('HTTP_IP_BUCKETS'):
                    self.http_counters.popitem(last=False)
                self.http_counters[address] = (window, 0)
            old_window, count = self.http_counters[address]
            if old_window != window:
                count = 0
            maximum = setting('HTTP_REQUESTS_PER_MINUTE')
            self.http_counters[address] = (window, min(count + 1, maximum + 1))
            self.http_counters.move_to_end(address)
        if count >= maximum:
            retry = max(1, int((window + 1) * 60 - instant) + 1)
            raise HTTPException(
                429,
                {'code': 'rate_limited', 'retry_after': retry},
                headers={'Retry-After': str(retry)},
            )

    async def __call__(self, scope, receive, send):
        kind = scope['type']
        if kind not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        address = (scope.get('client') or ('unknown', 0))[0]
        if kind == 'websocket':
            return await self.websocket(scope, receive, send, address)
        with self.lock:
            admitted = self.http_active < setting('HTTP_MAX_CONCURRENT')
            if admitted:
                self.http_active += 1

        async def safe_send(message):
            if message['type'] == 'http.response.start':
                message = {
                    **message,
                    'headers': [
                        *message.get('headers', []),
                        (b'x-content-type-options', b'nosniff'),
                        (b'x-frame-options', b'DENY'),
                        (b'referrer-policy', b'same-origin'),
                        (
                            b'content-security-policy',
                            b"frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
                        ),
                    ],
                }
                if scope.get('scheme') == 'https':
                    message['headers'].append((b'strict-transport-security', b'max-age=15552000'))
            await send(message)

        async def reject(status, detail, headers=None):
            await JSONResponse({'detail': detail}, status_code=status, headers=headers)(
                scope, receive, safe_send
            )

        if not admitted:
            return await reject(503, 'Server is busy; retry shortly', {'Retry-After': '1'})
        try:
            if len(scope.get('query_string', b'')) > 8192 or len(scope.get('path', '')) > 4096:
                return await reject(414, 'Request target is too long')
            request_headers = Headers(scope=scope)
            if (
                len(scope.get('headers', [])) > 100
                or sum(len(key) + len(value) for key, value in scope.get('headers', [])) > 32_768
            ):
                return await reject(431, 'Request headers are too large')
            maximum = setting('MAX_REQUEST_BODY_BYTES')
            lengths = request_headers.getlist('content-length')
            if lengths:
                try:
                    declared = int(lengths[0])
                except ValueError:
                    return await reject(400, 'Invalid Content-Length')
                if len(lengths) != 1 or declared < 0:
                    return await reject(400, 'Invalid Content-Length')
                if declared > maximum:
                    return await reject(413, 'Request body is too large')
            # Cookie-based SQLAdmin actions need origin checks; bearer-token API
            # requests do not rely on ambient browser credentials.
            if (
                scope.get('method') in {'POST', 'PUT', 'PATCH', 'DELETE'}
                and scope.get('path', '').startswith('/admin/')
                and 'session=' in request_headers.get('cookie', '')
            ):
                origin = request_headers.get('origin')
                own = f'{scope.get("scheme", "http")}://{request_headers.get("host", "")}'
                allowed = {
                    value.strip() for value in os.getenv('CORS_ALLOWED_ORIGINS', '').split(';')
                }
                if (origin and origin != own and origin not in allowed) or request_headers.get(
                    'sec-fetch-site'
                ) == 'cross-site':
                    return await reject(403, 'Cross-site admin request rejected')
            try:
                path = scope.get('path', '')
                cheap_read = scope.get('method') in {'GET', 'HEAD'} and (
                    path == '/' or path.startswith('/admin/statics/')
                )
                if not cheap_read:
                    self.http_quota(address)
            except HTTPException as exc:
                return await reject(exc.status_code, exc.detail, exc.headers)
            chunks, size = [], 0
            try:
                async with asyncio.timeout(setting('REQUEST_BODY_TIMEOUT')):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return
                        chunk = message.get('body', b'')
                        size += len(chunk)
                        if size > maximum:
                            return await reject(413, 'Request body is too large')
                        chunks.append(chunk)
                        if not message.get('more_body', False):
                            break
            except TimeoutError:
                return await reject(408, 'Request body timed out')
            body = b''.join(chunks)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                return await receive()

            await self.app(scope, replay, safe_send)
        finally:
            with self.lock:
                self.http_active -= 1

    async def websocket(self, scope, receive, send, address):
        address = client_network(address)
        with self.lock:
            admitted = self.ws_active < setting('WS_MAX_CONNECTIONS') and self.ws_clients.get(
                address, 0
            ) < setting('WS_MAX_PER_IP')
            if admitted:
                self.ws_active += 1
                self.ws_clients[address] = self.ws_clients.get(address, 0) + 1
        if not admitted:
            await send({'type': 'websocket.close', 'code': 1013})
            return
        try:

            async def bounded_receive():
                message = await receive()
                if message['type'] == 'websocket.receive':
                    payload = message.get('bytes') or (message.get('text') or '').encode('utf-8')
                    if len(payload) > 16_384:
                        await send({'type': 'websocket.close', 'code': 1009})
                        raise WebSocketDisconnect(1009)
                return message

            await self.app(scope, bounded_receive, send)
        finally:
            with self.lock:
                self.ws_active -= 1
                self.ws_clients[address] -= 1
                if not self.ws_clients[address]:
                    del self.ws_clients[address]
