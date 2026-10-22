"""Independent WebSocket transport; chat business logic resides in chat_service.py."""
import asyncio
import logging
import os
import uuid
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from mysite.api.chat_auth import client_by_token
from mysite.database.db import SessionLocal
from mysite.api.chat_service import owned, process_message

router = APIRouter(tags=['KYRGYZGO AI WebSocket'])
log = logging.getLogger(__name__)


def public_http_error(exc: HTTPException):
    detail = str(exc.detail)
    if exc.status_code == 404:
        return 'session_not_found', 'Беседа не найдена.', True
    if exc.status_code == 401 and 'истекла' in detail.casefold():
        return 'session_expired', 'Сессия входа истекла. Войдите снова.', True
    if exc.status_code in (401, 403):
        return 'authentication_failed', 'Не удалось подтвердить вход.', True
    if exc.status_code == 409:
        return 'booking_conflict', detail, False
    return 'request_invalid', detail, False


def authenticate_session(session_id, token):
    with SessionLocal() as db:
        client = client_by_token(db, token)
        owned(db, session_id, client.id)
        return client.id


@router.websocket('/ws/chat/{session_id}')
async def socket(websocket: WebSocket, session_id: str):
    allowed = {v.strip() for v in os.getenv('CHAT_ALLOWED_ORIGINS',
              'http://127.0.0.1:3000;http://localhost:3000').split(';') if v.strip()}
    if websocket.headers.get('origin') not in allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=30)
        token = (first.get('token') if isinstance(first, dict)
                 and first.get('type') == 'auth' else None)
        client_id = await asyncio.to_thread(authenticate_session, session_id, token)
        await websocket.send_json({'type': 'connected', 'session_id': session_id})
    except HTTPException as exc:
        code, message, _ = public_http_error(exc)
        await websocket.send_json({'type': 'error', 'code': code, 'message': message})
        await websocket.close(code=1008)
        return
    except (asyncio.TimeoutError, ValueError, TypeError):
        await websocket.send_json({
            'type': 'error', 'code': 'authentication_failed',
            'message': 'Не удалось подтвердить вход.'
        })
        await websocket.close(code=1008)
        return
    except WebSocketDisconnect:
        return
    except Exception:
        log.exception('WebSocket authentication failure')
        await websocket.close(code=1011)
        return

    # Sequential execution on each connection. Service layer also serializes same session locally.
    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except ValueError:
            await websocket.send_json({
                'type': 'error', 'code': 'invalid_message',
                'message': 'Некорректный JSON.'
            })
            continue
        message = data.get('message') if isinstance(data, dict) and data.get('type') == 'message' else None
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            await websocket.send_json({
                'type': 'error', 'code': 'invalid_message',
                'message': 'Введите сообщение (1–2000 символов).'
            })
            continue
        await websocket.send_json({'type': 'typing', 'status': True})
        message_id = str(uuid.uuid4())
        await websocket.send_json({'type': 'message_start', 'message_id': message_id})

        async def send_chunk(chunk: str, current_message_id=message_id):
            if chunk:
                await websocket.send_json({
                    'type': 'message_delta',
                    'message_id': current_message_id,
                    'delta': chunk,
                })

        try:
            result = await asyncio.wait_for(
                process_message(session_id, client_id, token, message.strip(),
                                on_chunk=send_chunk), timeout=180)
            if result.get('booking_preview'):
                await websocket.send_json({
                    'type': 'booking_preview', **result['booking_preview']
                })
            await websocket.send_json({
                'type': 'message_end', 'message_id': message_id,
                'revision': result['revision'],
                'booking_intent': result['booking_intent'],
                'stage': result.get('stage', 'consultation')
            })
            if result.get('booking_submitted'):
                await websocket.send_json({
                    'type': 'booking_submitted', **result['booking_submitted']
                })
        except HTTPException as exc:
            code, error_message, close = public_http_error(exc)
            await websocket.send_json({
                'type': 'error', 'code': code, 'message': error_message
            })
            if close:
                await websocket.close(code=1008)
                return
        except asyncio.TimeoutError:
            log.warning('AI timed out for session %s', session_id)
            await websocket.send_json({
                'type': 'error', 'code': 'ai_timeout',
                'message': 'Ответ занимает слишком много времени. Попробуйте ещё раз.'
            })
        except Exception as exc:
            log.exception('Chat processing failed for session %s', session_id)
            error_name = type(exc).__name__
            error_text = str(exc)
            if 'RateLimit' in error_name or 'RESOURCE_EXHAUSTED' in error_text:
                code = 'ai_rate_limit'
                message = 'Лимит AI временно исчерпан. Попробуйте позже.'
            elif 'GoogleAPI' in error_name or 'UNAVAILABLE' in error_text:
                code = 'ai_unavailable'
                message = 'AI-консультант временно недоступен. Попробуйте позже.'
            else:
                code = 'internal_error'
                message = 'Не удалось обработать запрос. Попробуйте ещё раз.'
            await websocket.send_json({
                'type': 'error', 'code': code, 'message': message
            })
        finally:
            try:
                await websocket.send_json({'type': 'typing', 'status': False})
            except (RuntimeError, WebSocketDisconnect):
                return
