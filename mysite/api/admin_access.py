"""Check upload authentication before reading the request body."""

import binascii
import json
from base64 import b64decode

from itsdangerous import BadSignature, TimestampSigner
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

UPLOAD_PATHS = {'/admin/media/upload', '/admin/media/video-upload'}


def upload_admin_allowed(scope) -> bool:
    # Локальные импорты не связывают middleware с загрузкой
    # модулей API при импорте main.py.
    from mysite.admin.credentials import SECRET_KEY
    from mysite.api.admin_sessions import setting, sql_session_admin
    from mysite.database.db import SessionLocal

    request = Request(scope)

    # Загрузка из SQLAdmin использует подписанную session-cookie.
    cookie = request.cookies.get('session')
    if not cookie:
        return False

    try:
        signed_data = TimestampSigner(SECRET_KEY).unsign(
            cookie.encode('utf-8'), max_age=setting('ADMIN_SESSION_HOURS') * 3600
        )
        session = json.loads(b64decode(signed_data, validate=True))

        if not isinstance(session, dict):
            return False

        admin_id = session.get('admin_id')
        if type(admin_id) is not int or admin_id <= 0:
            return False
    except (BadSignature, binascii.Error, ValueError, TypeError, UnicodeError):
        return False

    with SessionLocal() as db:
        admin = sql_session_admin(db, session)
        return bool(admin and admin.role in {'owner', 'catalog_editor'})


class AdminAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        is_upload = (
            scope['type'] == 'http'
            and scope.get('method') == 'POST'
            and scope.get('path', '').rstrip('/') in UPLOAD_PATHS
        )

        if is_upload:
            allowed = await run_in_threadpool(upload_admin_allowed, scope)

            if not allowed:
                response = JSONResponse(
                    {'detail': 'Требуется вход администратора'}, status_code=401
                )
                return await response(scope, receive, send)

        return await self.app(scope, receive, send)
