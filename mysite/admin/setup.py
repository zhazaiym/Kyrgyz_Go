import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from sqladmin import Admin as SQLAdmin
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from mysite.admin.realtime import admin_requests_websocket
from mysite.api.admin import SECRET_KEY, dummy_admin_hash, verify_password
from mysite.api.media import save_upload
from mysite.api.rate_limit import enforce_login_attempt
from mysite.database.db import SessionLocal, engine
from mysite.database.models import Admin as AdminModel

from .views import (AboutAdmin, AboutSectionAdmin, AdminAdmin, ChatRequestAdmin, ContactAdmin,
                    DistrictAdmin, FAQAdmin, HelicopterImageAdmin, HelicopterTourAdmin, HotelAdmin,
                    HotelImageAdmin, RegionAdmin, TourAdmin, TourCategoryAdmin, TourImageAdmin,
                    TourProgramAdmin, TransportAdmin, TransportImageAdmin, TrekkingAdmin,
                    TrekkingImageAdmin, TrekkingProgramAdmin)


class AdminAuthBackend(AuthenticationBackend):
    def __init__(self):
        super().__init__(
            secret_key=SECRET_KEY,
            max_age=None,
            same_site='strict',
            https_only=os.getenv('ADMIN_COOKIE_SECURE', 'true').lower() == 'true',
        )

    @staticmethod
    def login_identity(request, username, password):
        with SessionLocal() as db:
            admin = db.query(AdminModel).filter(AdminModel.username == username).first()
            admin_id = admin.id if admin else None
            account_key = (
                f'admin:{admin_id}'
                if admin_id is not None
                else (f'unknown:{username.strip().casefold()}')
            )
            is_active = bool(admin and admin.is_active)
            password_hash = admin.hashed_password if admin else dummy_admin_hash
        enforce_login_attempt('admin-login', request, account_key)
        valid = verify_password(password, password_hash)
        if not admin_id or not valid:
            return None
        return admin_id if is_active else None

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get('username', '')).strip()
        password = str(form.get('password', ''))
        if not 1 <= len(username) <= 100 or not 1 <= len(password) <= 128:
            return False
        try:
            identity = await run_in_threadpool(self.login_identity, request, username, password)
        except HTTPException as exc:
            if exc.status_code == 429:
                return False
            raise

        if identity is None:
            return False
        request.session.clear()
        request.session['admin_id'] = identity
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    @staticmethod
    def active_admin(admin_id):
        with SessionLocal() as db:
            admin = db.get(AdminModel, admin_id)
            return bool(admin and admin.is_active)

    async def authenticate(self, request: Request) -> bool:
        admin_id = request.session.get('admin_id')
        if admin_id is None:
            return False
        return await run_in_threadpool(self.active_admin, admin_id)


async def upload_image(request: Request):
    admin_id = request.session.get('admin_id')
    if admin_id is None or not await run_in_threadpool(AdminAuthBackend.active_admin, admin_id):
        return JSONResponse({'detail': 'Админ катары кириңиз'}, status_code=401)
    form = await request.form(max_files=1, max_fields=1)
    upload = form.get('file')
    if not hasattr(upload, 'read'):
        return JSONResponse({'detail': 'Сүрөт тандалган жок'}, status_code=400)
    try:
        url = await save_upload(request, upload)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    return JSONResponse({'url': url}, status_code=201)


def setup_admin(auth_app: FastAPI):
    admin = SQLAdmin(
        auth_app,
        engine,
        authentication_backend=AdminAuthBackend(),
        templates_dir=str(Path(__file__).resolve().parent / 'templates'),
    )
    admin.admin.router.add_websocket_route(
        '/ws/requests', admin_requests_websocket, name='request_notifications'
    )
    admin.admin.router.add_route('/media/upload', upload_image, methods=['POST'])
    admin.add_view(AdminAdmin)
    admin.add_view(AboutAdmin)
    admin.add_view(AboutSectionAdmin)
    admin.add_view(TourCategoryAdmin)
    admin.add_view(TourImageAdmin)
    admin.add_view(TourAdmin)
    admin.add_view(TourProgramAdmin)
    admin.add_view(RegionAdmin)
    admin.add_view(DistrictAdmin)
    admin.add_view(HotelAdmin)
    admin.add_view(HotelImageAdmin)
    admin.add_view(TransportAdmin)
    admin.add_view(TransportImageAdmin)
    admin.add_view(HelicopterTourAdmin)
    admin.add_view(HelicopterImageAdmin)
    admin.add_view(TrekkingAdmin)
    admin.add_view(TrekkingImageAdmin)
    admin.add_view(TrekkingProgramAdmin)
    admin.add_view(ContactAdmin)
    admin.add_view(FAQAdmin)
    admin.add_view(ChatRequestAdmin)
    return admin
