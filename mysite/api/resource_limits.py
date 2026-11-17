"""Bounded admission, request sizes and cheap rejection before application work."""

import asyncio
import time
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from functools import lru_cache
from threading import Lock

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from mysite.api.errors import STATUS_CODES, error_detail
from mysite.api.network_identity import client_network, rate_limits_enabled
from mysite.api.observability import record_websocket_connection
from mysite.settings import parse_number

RESOURCE_LIMITS = {
    'AI_MAX_CONCURRENT': (4, 32),
    'AI_MAX_PER_CLIENT': (2, 32),
    'AI_MAX_PER_IP': (3, 32),
    'AI_QUEUE_SECONDS': (5, 30),
    'AI_DAILY_TOKENS': (20_000_000, 2_000_000_000),
    'AI_CLIENT_DAILY_TOKENS': (1_000_000, 2_000_000_000),
    'AI_IP_DAILY_TOKENS': (3_000_000, 2_000_000_000),
    'AUTH_MAX_CONCURRENT': (4, 16),
    'HTTP_MAX_CONCURRENT': (64, 512),
    'HTTP_REQUESTS_PER_MINUTE': (120, 100_000),
    # Reading the catalogue is cheap and a page makes many reads; writes keep the lower limit.
    'HTTP_READS_PER_MINUTE': (600, 100_000),
    'HTTP_IP_BUCKETS': (8192, 65_536),
    'MAX_REQUEST_BODY_BYTES': (1_048_576, 16_777_216),
    'MAX_IMAGE_UPLOAD_BYTES': (10_485_760, 33_554_432),
    'MAX_VIDEO_UPLOAD_BYTES': (104_857_600, 1_073_741_824),
    'REQUEST_BODY_TIMEOUT': (10, 60),
    'UPLOAD_MAX_SECONDS': (900, 3600),
    'WS_MAX_CONNECTIONS': (64, 512),
    'WS_MAX_PER_IP': (8, 64),
    'WS_MAX_PER_CLIENT': (8, 64),
    'WS_IDLE_SECONDS': (600, 3600),
    'WS_AUTH_SECONDS': (10, 30),
}
IMAGE_UPLOAD_PATHS = {'/admin/media/', '/admin/media/upload', '/chat/images/'}
VIDEO_UPLOAD_PATHS = {'/admin/media/videos/', '/admin/media/video-upload'}


@lru_cache(maxsize=len(RESOURCE_LIMITS))
def setting(name):
    default, maximum = RESOURCE_LIMITS[name]
    return parse_number(name, default, 1, maximum)


@lru_cache(maxsize=1)
def validate_resource_settings():
    for name in RESOURCE_LIMITS:
        setting(name)


# One Uvicorn worker (DEPLOY.md): these counters live in the memory of this process.
_ai_lock = Lock()
_ai_active = 0
_ai_owners = {}  # replies being written or waiting for a place, per client and per address
_ai_waiters = set()


def _ai_busy():
    return HTTPException(503, error_detail('service_unavailable'), headers={'Retry-After': '5'})


def _owner_limit(owner):
    # One owner never gets every place, whatever the settings say.
    share = setting('AI_MAX_PER_IP' if owner.startswith('ip:') else 'AI_MAX_PER_CLIENT')
    return min(share, max(1, setting('AI_MAX_CONCURRENT') - 1))


def _wake_ai_waiters():
    for waiter in tuple(_ai_waiters):
        try:
            waiter.get_loop().call_soon_threadsafe(
                lambda waiter=waiter: waiter.done() or waiter.set_result(None)
            )
        except RuntimeError:  # its event loop is already closed
            _ai_waiters.discard(waiter)


@asynccontextmanager
async def ai_capacity(*owners):
    """A place at the model: AI_MAX_CONCURRENT replies for everyone and a smaller
    share for each owner ("client:7", "ip:203.0.113.0").

    An owner over its share is refused at once. When only the common places
    are taken, the caller waits up to AI_QUEUE_SECONDS for one to become free.
    """
    global _ai_active
    owners = tuple(owner for owner in owners if owner)
    with _ai_lock:
        if any(_ai_owners.get(owner, 0) >= _owner_limit(owner) for owner in owners):
            raise _ai_busy()
        for owner in owners:
            _ai_owners[owner] = _ai_owners.get(owner, 0) + 1
    loop = asyncio.get_running_loop()
    deadline = loop.time() + setting('AI_QUEUE_SECONDS')
    admitted = False
    try:
        while not admitted:
            with _ai_lock:
                admitted = _ai_active < setting('AI_MAX_CONCURRENT')
                if admitted:
                    _ai_active += 1
                    break
                waiter = loop.create_future()
                _ai_waiters.add(waiter)
            try:
                await asyncio.wait_for(waiter, timeout=max(0, deadline - loop.time()))
            except TimeoutError:
                raise _ai_busy() from None
            finally:
                _ai_waiters.discard(waiter)
        yield
    finally:
        with _ai_lock:
            if admitted:
                _ai_active -= 1
            for owner in owners:
                _ai_owners[owner] -= 1
                if not _ai_owners[owner]:
                    del _ai_owners[owner]
            _wake_ai_waiters()


SECURITY_HEADERS = [
    (b'x-content-type-options', b'nosniff'),
    (b'x-frame-options', b'DENY'),
    (b'referrer-policy', b'same-origin'),
    (b'content-security-policy', b"frame-ancestors 'none'; object-src 'none'; base-uri 'self'"),
]
HTTPS_ONLY = [(b'strict-transport-security', b'max-age=15552000')]


def body_limit(scope):
    if scope.get('method') == 'POST' and scope.get('path') in IMAGE_UPLOAD_PATHS:
        return setting('MAX_IMAGE_UPLOAD_BYTES') + 65_536
    if scope.get('method') == 'POST' and scope.get('path') in VIDEO_UPLOAD_PATHS:
        return setting('MAX_VIDEO_UPLOAD_BYTES') + 65_536
    return setting('MAX_REQUEST_BODY_BYTES')


def refused_head(scope, headers, maximum):
    """The status that refuses a request by its target and headers alone, or None."""
    if len(scope.get('query_string', b'')) > 8192 or len(scope.get('path', '')) > 4096:
        return 414
    raw = scope.get('headers', [])
    if len(raw) > 100 or sum(len(key) + len(value) for key, value in raw) > 32_768:
        return 431
    lengths = headers.getlist('content-length')
    if lengths:
        try:
            declared = int(lengths[0])
        except ValueError:
            return 400
        if len(lengths) != 1 or declared < 0:
            return 400
        if declared > maximum:
            return 413
    # Cookie-based SQLAdmin actions need origin checks; bearer-token API
    # requests do not rely on ambient browser credentials.
    if (
        scope.get('method') in {'POST', 'PUT', 'PATCH', 'DELETE'}
        and scope.get('path', '').startswith('/admin/')
        and 'session=' in headers.get('cookie', '')
    ):
        origin = headers.get('origin')
        own = f'{scope.get("scheme", "http")}://{headers.get("host", "")}'
        if (origin and origin != own) or headers.get('sec-fetch-site') == 'cross-site':
            return 403
    return None


def cheap_read(scope):
    path = scope.get('path', '')
    return scope.get('method') in {'GET', 'HEAD'} and (
        path == '/' or path.startswith(('/admin/statics/', '/media/'))
    )


def upload_receive(receive, maximum):
    size = 0
    # A large file on a slow line may take minutes; what is refused is a
    # sender that stops sending (REQUEST_BODY_TIMEOUT between pieces).
    deadline = asyncio.get_running_loop().time() + setting('UPLOAD_MAX_SECONDS')

    async def bounded_upload_receive():
        nonlocal size
        left = deadline - asyncio.get_running_loop().time()
        try:
            message = await asyncio.wait_for(
                receive(), timeout=max(0, min(setting('REQUEST_BODY_TIMEOUT'), left))
            )
        except TimeoutError:
            raise HTTPException(408, 'Request body timed out') from None
        size += len(message.get('body', b''))
        if size > maximum:
            raise HTTPException(413, 'Request body is too large')
        return message

    return bounded_upload_receive


async def buffered_body(receive, maximum):
    """Read the whole body within REQUEST_BODY_TIMEOUT; None when the client left."""
    chunks, size = deque(), 0
    try:
        async with asyncio.timeout(setting('REQUEST_BODY_TIMEOUT')):
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return None
                chunk = message.get('body', b'')
                size += len(chunk)
                if size > maximum:
                    raise HTTPException(413)
                chunks.append(chunk)
                if not message.get('more_body', False):
                    break
    except TimeoutError:
        raise HTTPException(408) from None
    delivered = False

    async def replay():
        nonlocal delivered
        if chunks:
            chunk = chunks.popleft()
            delivered = not chunks
            return {'type': 'http.request', 'body': chunk, 'more_body': bool(chunks)}
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        return await receive()

    return replay


class ResourceLimitsMiddleware:
    def __init__(self, app):
        validate_resource_settings()
        self.app = app
        self.lock = Lock()
        self.http_active = 0
        self.ws_active = 0
        self.ws_clients = {}
        self.http_counters = OrderedDict()

    def http_quota(self, address, method='POST'):
        if not rate_limits_enabled():
            return
        reading = method in {'GET', 'HEAD', 'OPTIONS'}
        address = (client_network(address), reading)
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
            maximum = setting('HTTP_READS_PER_MINUTE' if reading else 'HTTP_REQUESTS_PER_MINUTE')
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
                extra = SECURITY_HEADERS + (HTTPS_ONLY if scope.get('scheme') == 'https' else [])
                message = {**message, 'headers': [*message.get('headers', []), *extra]}
            await send(message)

        async def reject(status, detail=None, headers=None):
            detail = detail or error_detail(STATUS_CODES.get(status, 'invalid_request'))
            await JSONResponse({'detail': detail}, status_code=status, headers=headers)(
                scope, receive, safe_send
            )

        if not admitted:
            return await reject(503, headers={'Retry-After': '1'})
        try:
            maximum = body_limit(scope)
            refused = refused_head(scope, Headers(scope=scope), maximum)
            if refused:
                return await reject(refused)
            if not cheap_read(scope):
                try:
                    self.http_quota(address, scope.get('method'))
                except HTTPException as exc:
                    return await reject(exc.status_code, exc.detail, exc.headers)
            if (
                scope.get('method') == 'POST'
                and scope.get('path') in IMAGE_UPLOAD_PATHS | VIDEO_UPLOAD_PATHS
            ):
                return await self.app(scope, upload_receive(receive, maximum), safe_send)
            try:
                replay = await buffered_body(receive, maximum)
            except HTTPException as exc:
                return await reject(exc.status_code)
            if replay is not None:
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
        accepted = False

        async def track_connection(message):
            nonlocal accepted
            if message['type'] == 'websocket.accept' and not accepted:
                accepted = True
                record_websocket_connection(True)
            await send(message)

        try:

            async def bounded_receive():
                message = await receive()
                if message['type'] == 'websocket.receive':
                    payload = message.get('bytes') or (message.get('text') or '').encode('utf-8')
                    if len(payload) > 16_384:
                        await send({'type': 'websocket.close', 'code': 1009})
                        raise WebSocketDisconnect(1009)
                return message

            await self.app(scope, bounded_receive, track_connection)
        finally:
            if accepted:
                record_websocket_connection(False)
            with self.lock:
                self.ws_active -= 1
                self.ws_clients[address] -= 1
                if not self.ws_clients[address]:
                    del self.ws_clients[address]
