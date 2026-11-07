"""Authenticated admin notifications for newly submitted travel requests."""

import asyncio
import logging
import threading
from contextlib import suppress
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocket, WebSocketDisconnect

from mysite.database.db import SessionLocal
from mysite.database.models import Admin

logger = logging.getLogger(__name__)
_clients = set()
_clients_lock = threading.Lock()


def publish_new_request(request_id: int) -> None:
    """Send a small event to connected admins after a request has committed."""
    event = {'type': 'new_request', 'request_id': request_id}
    with _clients_lock:
        clients = tuple(_clients)
    for loop, queue in clients:
        if loop.is_running():
            try:
                loop.call_soon_threadsafe(_enqueue, queue, event)
            except RuntimeError:
                logger.debug('Admin notification loop closed before event delivery')


def _enqueue(queue: asyncio.Queue, event: dict) -> None:
    if queue.full():
        with suppress(asyncio.QueueEmpty):
            queue.get_nowait()
    queue.put_nowait(event)


def _eligible_admin(admin_id) -> bool:
    with SessionLocal() as db:
        admin = db.get(Admin, admin_id)
        return bool(admin and admin.is_active and admin.role in {'owner', 'manager'})


async def admin_requests_websocket(websocket: WebSocket) -> None:
    origin = websocket.headers.get('origin')
    if origin:
        parsed_origin = urlsplit(origin)
        if parsed_origin.netloc != websocket.headers.get('host'):
            await websocket.close(code=1008)
            return

    session = websocket.scope.get('session', {})
    admin_id = session.get('admin_id')
    if (
        admin_id is None
        or not session.get('admin_mfa')
        or not await run_in_threadpool(_eligible_admin, admin_id)
    ):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=100)
    client = (loop, queue)
    with _clients_lock:
        _clients.add(client)

    async def deliver_events():
        while True:
            await websocket.send_json(await queue.get())

    sender = asyncio.create_task(deliver_events())
    try:
        while True:
            message = await websocket.receive()

            if message['type'] == 'websocket.disconnect':
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception('Admin request notification WebSocket failed')
    finally:
        with _clients_lock:
            _clients.discard(client)
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender
