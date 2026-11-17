"""Independent WebSocket transport; chat business logic resides in chat_service.py."""

import asyncio
import json
import logging
import time
import uuid
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from mysite.api.chat_images import finish_image, take_image
from mysite.api.chat_service import ReplyStream, owned, process_message
from mysite.api.client_auth import SessionExpired, client_by_token
from mysite.api.errors import STATUS_CODES, error_detail
from mysite.api.network_identity import client_network
from mysite.api.observability import record_chat_message
from mysite.api.origin_config import configured_origins
from mysite.api.rate_limit import enforce_chat_message_limits, enforce_rate_limit
from mysite.api.resource_limits import setting
from mysite.database.db import SessionLocal

chat_ws_router = APIRouter(tags=['KYRGYZGO AI WebSocket'])
log = logging.getLogger(__name__)
# One Uvicorn worker (DEPLOY.md): open chat connections of each client, counted after login.
_client_connections = {}


class AuthenticationFrame(BaseModel):
    type: Literal['auth']
    token: str = Field(strict=True, min_length=1, max_length=256)


class _Closed(Exception):
    """The server has closed the connection; stop serving it."""


def public_http_error(exc: HTTPException):
    """WebSocket error code, text for the client and whether the connection must close.

    The decision follows the status and the kind of error, never its wording;
    the text is the catalogue message, never the detail object itself.
    """
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    message = detail.get('message')
    if not isinstance(message, str):
        message = error_detail(STATUS_CODES.get(exc.status_code, 'invalid_request'))['message']
    if exc.status_code == 404:
        return 'session_not_found', 'Беседа не найдена.', True
    if isinstance(exc, SessionExpired):
        return 'session_expired', 'Сессия входа истекла. Войдите снова.', True
    if exc.status_code in (401, 403):
        return 'authentication_failed', 'Не удалось подтвердить вход.', True
    if exc.status_code == 409:
        return 'booking_conflict', message, False
    if exc.status_code == 503:
        return 'ai_busy', 'AI сейчас занят. Повторите запрос немного позже.', False
    return 'request_invalid', message, False


def _rate_limited_frame(exc: HTTPException):
    return {
        'type': 'error',
        'code': 'rate_limited',
        'message': 'Слишком много сообщений. Повторите позже.',
        'retry_after': int((exc.headers or {}).get('Retry-After', '60')),
    }


def authenticate_session(session_id, token):
    with SessionLocal() as db:
        client = client_by_token(db, token)
        owned(db, session_id, client.id)
        return client.id


async def receive_json_text(websocket):
    frame = await websocket.receive()
    if frame['type'] == 'websocket.disconnect':
        raise WebSocketDisconnect(frame.get('code', 1000))
    text = frame.get('text')
    if not isinstance(text, str):
        raise ValueError('A JSON text frame is required')
    return json.loads(text)


async def unavailable(websocket):
    await websocket.send_json(
        {
            'type': 'error',
            'code': 'service_unavailable',
            'message': 'Сервис временно недоступен. Повторите подключение позже.',
        }
    )
    await websocket.close(code=1011)


async def _reject(websocket, code, message, close_code=1008):
    await websocket.send_json({'type': 'error', 'code': code, 'message': message})
    await websocket.close(code=close_code)
    raise _Closed


async def process_connected(websocket, operation, pending):
    """Observe disconnect while working, retaining at most eight queued frames."""

    async def read():
        try:
            return await receive_json_text(websocket)
        except ValueError:
            return ValueError('Invalid JSON frame')

    work = asyncio.create_task(operation)
    incoming = asyncio.create_task(read())
    try:
        while True:
            done, _ = await asyncio.wait({work, incoming}, return_when=asyncio.FIRST_COMPLETED)
            if incoming in done:
                frame = incoming.result()  # Disconnect cancels the work in finally.
                if len(pending) >= 8:
                    await websocket.close(code=1008)
                    raise WebSocketDisconnect(1008)
                pending.append(frame)
                if work not in done:
                    incoming = asyncio.create_task(read())
            if work in done:
                return await work
    finally:
        for task in (work, incoming):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, incoming, return_exceptions=True)


@chat_ws_router.websocket('/ws/chat/{session_id}')
async def socket(websocket: WebSocket, session_id: str):
    try:
        await socket_session(websocket, session_id)
    except (WebSocketDisconnect, OSError):
        return


async def _handshake(websocket):
    """Accept the connection and return the caller's network; raises _Closed when refused."""
    allowed = set(
        configured_origins('CHAT_ALLOWED_ORIGINS', 'http://127.0.0.1:3000;http://localhost:3000')
    )
    if websocket.headers.get('origin') not in allowed:
        await websocket.close(code=1008)
        raise _Closed
    client_address = getattr(websocket, 'client', None)
    network = client_network(client_address.host if client_address else 'unknown')
    try:
        await asyncio.to_thread(
            enforce_rate_limit,
            'websocket-handshake',
            f'ip:{network}',
            max_requests=30,
            window_seconds=60,
        )
    except HTTPException:
        await websocket.close(code=1008)
        raise _Closed from None
    except SQLAlchemyError:
        log.exception('WebSocket handshake limiter failed')
        await websocket.accept()
        await unavailable(websocket)
        raise _Closed from None
    await websocket.accept()
    return network


async def _login(websocket, session_id):
    """The client and token from the first frame; raises _Closed when login fails."""
    try:
        first = await asyncio.wait_for(
            receive_json_text(websocket), timeout=setting('WS_AUTH_SECONDS')
        )
        token = AuthenticationFrame.model_validate(first).token
        client_id = await asyncio.to_thread(authenticate_session, session_id, token)
    except HTTPException as exc:
        code, message, _ = public_http_error(exc)
        await _reject(websocket, code, message)
    except (asyncio.TimeoutError, ValueError, TypeError):
        await _reject(websocket, 'authentication_failed', 'Не удалось подтвердить вход.')
    except (SQLAlchemyError, KeyError, RuntimeError, OSError):
        log.exception('WebSocket authentication failure')
        await unavailable(websocket)
        raise _Closed from None
    return client_id, token


def _admit_client(client_id):
    """Count one more open chat of the client; False when it already holds its share."""
    if _client_connections.get(client_id, 0) >= setting('WS_MAX_PER_CLIENT'):
        return False
    _client_connections[client_id] = _client_connections.get(client_id, 0) + 1
    return True


def _release_client(client_id):
    _client_connections[client_id] -= 1
    if not _client_connections[client_id]:
        del _client_connections[client_id]


async def socket_session(websocket: WebSocket, session_id: str):
    try:
        network = await _handshake(websocket)
        client_id, token = await _login(websocket, session_id)
        if not _admit_client(client_id):
            await _reject(
                websocket,
                'too_many_connections',
                'Открыто слишком много окон чата. Закройте лишние и подключитесь снова.',
            )
    except _Closed:
        return
    connection = SimpleNamespace(
        websocket=websocket,
        session_id=session_id,
        client_id=client_id,
        token=token,
        network=network,
        pending=[],
        strikes={'invalid': 0, 'throttled': 0},
    )
    try:
        await websocket.send_json({'type': 'connected', 'session_id': session_id})
        # Sequential execution on each connection. Service layer also serializes same session locally.
        while True:
            message, image_id = await _next_message(connection)
            if await _within_limits(connection) and not await _reply(connection, message, image_id):
                return
    except _Closed:
        return
    finally:
        _release_client(client_id)


async def _warn(connection, kind, frame):
    """Send a recoverable error; the third of a kind in a row closes the connection."""
    connection.strikes[kind] += 1
    await connection.websocket.send_json(frame)
    if connection.strikes[kind] >= 3:
        await connection.websocket.close(code=1008)
        raise _Closed


def _message_parts(data):
    """(text, image_id) of a valid message frame, otherwise None."""
    frame = data if isinstance(data, dict) and data.get('type') == 'message' else {}
    image_id = frame.get('image_id')
    message = frame.get('message', '' if image_id is not None else None)
    if (
        not isinstance(message, str)
        or len(message.strip()) > 2000
        or (image_id is None and not message.strip())
        or (image_id is not None and (not isinstance(image_id, str) or len(image_id) > 64))
    ):
        return None
    return message.strip(), image_id


async def _next_message(connection):
    """Wait for the next valid client message; a silent connection is closed."""
    websocket = connection.websocket
    while True:
        try:
            if connection.pending:
                data = connection.pending.pop(0)
            else:
                data = await asyncio.wait_for(
                    receive_json_text(websocket), timeout=setting('WS_IDLE_SECONDS')
                )
            if isinstance(data, ValueError):
                raise data
        except asyncio.TimeoutError:
            # A forgotten tab must not hold one of the few chat places.
            await _reject(
                websocket,
                'idle_timeout',
                'Соединение закрыто из-за простоя. Подключитесь снова, чтобы продолжить.',
                close_code=1000,
            )
        except ValueError:
            await _warn(
                connection,
                'invalid',
                {'type': 'error', 'code': 'invalid_message', 'message': 'Некорректный JSON.'},
            )
            continue
        parts = _message_parts(data)
        if parts is not None:
            return parts
        await _warn(
            connection,
            'invalid',
            {
                'type': 'error',
                'code': 'invalid_message',
                'message': 'Введите сообщение (1–2000 символов).',
            },
        )


async def _within_limits(connection):
    try:
        await asyncio.to_thread(enforce_chat_message_limits, connection.client_id)
    except HTTPException as exc:
        await _warn(connection, 'throttled', _rate_limited_frame(exc))
        return False
    except SQLAlchemyError:
        log.exception('WebSocket message limiter failed')
        await unavailable(connection.websocket)
        raise _Closed from None
    connection.strikes = {'invalid': 0, 'throttled': 0}
    return True


async def _send_result(websocket, message_id, result):
    if result.get('booking_preview'):
        await websocket.send_json({'type': 'booking_preview', **result['booking_preview']})
    await websocket.send_json(
        {
            'type': 'message_end',
            'message_id': message_id,
            'revision': result['revision'],
            'booking_intent': result['booking_intent'],
            'stage': result.get('stage', 'consultation'),
        }
    )
    if result.get('booking_submitted'):
        await websocket.send_json({'type': 'booking_submitted', **result['booking_submitted']})


async def _send_http_error(websocket, exc):
    """Tell the client about a refused message; True when the connection must close."""
    if exc.status_code == 429:
        await websocket.send_json(_rate_limited_frame(exc))
        return False
    code, message, close = public_http_error(exc)
    await websocket.send_json({'type': 'error', 'code': code, 'message': message})
    return close


async def _reply(connection, message, image_id):
    """Answer one message; False when the connection is finished."""
    websocket = connection.websocket
    session_id = connection.session_id
    image = None
    if image_id is not None:
        image = take_image(image_id, connection.client_id, session_id)
        if image is None:
            await websocket.send_json(
                {
                    'type': 'error',
                    'code': 'image_not_found',
                    'message': 'Фото не найдено или устарело. Загрузите его ещё раз.',
                }
            )
            return True
    photo_used = False
    message_id = str(uuid.uuid4())

    async def send_chunk(chunk: str):
        await websocket.send_json(
            {'type': 'message_delta', 'message_id': message_id, 'delta': chunk}
        )

    async def send_reset():
        await websocket.send_json({'type': 'message_reset', 'message_id': message_id})

    stream = ReplyStream(send_chunk, send_reset)
    message_started = time.perf_counter()
    message_outcome = 'internal_error'
    try:
        await websocket.send_json({'type': 'typing', 'status': True})
        await websocket.send_json({'type': 'message_start', 'message_id': message_id})
        result = await asyncio.wait_for(
            process_connected(
                websocket,
                process_message(
                    session_id,
                    connection.client_id,
                    connection.token,
                    message,
                    on_chunk=stream,
                    image=image,
                    network=connection.network,
                ),
                connection.pending,
            ),
            timeout=180,
        )
        message_outcome = 'success'
        photo_used = True
        await _send_result(websocket, message_id, result)
    except WebSocketDisconnect:
        message_outcome = 'disconnected'
        return False
    except AIError as exc:
        message_outcome = 'ai_error'
        log.warning('Chat provider error: %s', exc.code)
        await stream.reset()
        await websocket.send_json({'type': 'error', 'code': exc.code, 'message': exc.message})
    except HTTPException as exc:
        message_outcome = {409: 'conflict', 429: 'rate_limited'}.get(
            exc.status_code, 'internal_error'
        )
        await stream.reset()
        if await _send_http_error(websocket, exc):
            await websocket.close(code=1008)
            return False
    except asyncio.TimeoutError:
        message_outcome = 'timeout'
        log.warning('AI timed out for session %s', session_id)
        await stream.reset()
        await websocket.send_json(
            {
                'type': 'error',
                'code': 'ai_timeout',
                'message': 'Ответ занимает слишком много времени. Попробуйте ещё раз.',
            }
        )
    except (
        *PROVIDER_ERRORS,
        SQLAlchemyError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        OSError,
    ) as exc:
        message_outcome = 'internal_error'
        failure = classify_error(exc)
        log.error('Chat processing failed: %s (%s)', failure.code, type(exc).__name__)
        await stream.reset()
        await websocket.send_json(
            {'type': 'error', 'code': failure.code, 'message': failure.message}
        )
    finally:
        if image_id is not None:
            # After a failed reply the same photo can be sent again.
            finish_image(image_id, photo_used)
        record_chat_message(message_outcome, time.perf_counter() - message_started)
        try:
            await websocket.send_json({'type': 'typing', 'status': False})
        except (RuntimeError, WebSocketDisconnect):
            return False
    return True
