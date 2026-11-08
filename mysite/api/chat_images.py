"""Chat photos: validated in memory, handed once to Gemini, never written to disk or the DB."""

import secrets
import time
from io import BytesIO
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from mysite.api.chat_service import owned
from mysite.api.client_auth import current_client
from mysite.api.errors import error_detail
from mysite.api.media import check_upload_size, open_image
from mysite.api.rate_limit import enforce_rate_limit
from mysite.database.chat_models import ChatClient
from mysite.database.db import get_db

CHAT_IMAGE_PATH = '/chat/images'
CHAT_IMAGE_SIDE = 1536
CHAT_IMAGE_TTL_SECONDS = 600
MAX_PENDING_IMAGES = 64
MAX_PENDING_PER_CLIENT = 3

chat_images_router = APIRouter(tags=['KYRGYZGO AI Chat'])
# One Uvicorn worker (DEPLOY.md): a photo waits here until its chat message takes it.
_pending: dict[str, tuple[int, str, bytes, float]] = {}
_lock = Lock()


def encode_chat_image(content) -> bytes:
    image = open_image(content, CHAT_IMAGE_SIDE)
    try:
        output = BytesIO()
        image.save(output, 'WEBP', quality=85)
        return output.getvalue()
    finally:
        image.close()


def remember_image(client_id: int, session_id: str, data: bytes) -> str:
    now = time.monotonic()
    with _lock:
        for key in [key for key, entry in _pending.items() if entry[3] <= now]:
            del _pending[key]
        waiting = sum(entry[0] == client_id for entry in _pending.values())
        if len(_pending) >= MAX_PENDING_IMAGES or waiting >= MAX_PENDING_PER_CLIENT:
            raise HTTPException(429, error_detail('rate_limited'), headers={'Retry-After': '60'})
        image_id = secrets.token_urlsafe(16)
        _pending[image_id] = (client_id, session_id, data, now + CHAT_IMAGE_TTL_SECONDS)
    return image_id


def take_image(image_id: str, client_id: int, session_id: str) -> bytes | None:
    """Return the photo once to its owner in its session; None if unknown or expired."""
    with _lock:
        entry = _pending.get(image_id)
        if entry is None or entry[0] != client_id or entry[1] != session_id:
            return None
        del _pending[image_id]
    return entry[2] if entry[3] > time.monotonic() else None


@chat_images_router.post(CHAT_IMAGE_PATH, status_code=201)
async def upload_chat_image(
    request: Request, client: ChatClient = Depends(current_client), db: Session = Depends(get_db)
):
    async with request.form(max_files=1, max_fields=1) as form:
        session_id = form.get('session_id')
        upload = form.get('file')
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 36:
            raise HTTPException(400, detail=error_detail('invalid_request'))
        if not hasattr(upload, 'file'):
            raise HTTPException(400, detail=error_detail('invalid_request'))
        await run_in_threadpool(owned, db, session_id, client.id)
        await run_in_threadpool(
            enforce_rate_limit,
            'chat-image-upload',
            f'client:{client.id}',
            max_requests=30,
            window_seconds=3600,
        )
        await check_upload_size(upload)
        data = await run_in_threadpool(encode_chat_image, upload.file)
    image_id = remember_image(client.id, session_id, data)
    return {'image_id': image_id, 'expires_in': CHAT_IMAGE_TTL_SECONDS}
