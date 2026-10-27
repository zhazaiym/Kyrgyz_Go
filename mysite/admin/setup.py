import os

from fastapi import FastAPI, HTTPException, Request
from sqladmin import Admin as SQLAdmin
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool

from mysite.api.admin import SECRET_KEY, dummy_admin_hash, verify_password
from mysite.api.rate_limit import enforce_request_limits
from mysite.database.db import SessionLocal, engine
from mysite.database.models import Admin as AdminModel

from .views import (AboutAdmin, AboutSectionAdmin, AdminAdmin, ChatRequestAdmin, ContactAdmin,
                    DistrictAdmin, FAQAdmin, HelicopterImageAdmin, HelicopterTourAdmin, HotelAdmin,
                    HotelImageAdmin, RegionAdmin, TourAdmin, TourCategoryAdmin, TourImageAdmin,
                    TourProgramAdmin, TransportAdmin, TransportImageAdmin, TrekkingAdmin,
                    TrekkingImageAdmin, TrekkingProgramAdmin)


class AdminAuthBackend(AuthenticationBackend):
    @staticmethod
    def login_identity(request, username, password):
        enforce_request_limits(
            'admin-login', request, username, ip_limit=20, identity_limit=5, window_seconds=60
        )
        with SessionLocal() as db:
            admin = db.query(AdminModel).filter(AdminModel.username == username).first()
            valid = verify_password(password, admin.hashed_password if admin else dummy_admin_hash)
            return admin.id if admin and admin.is_active and valid else None

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

    async def authenticate(self, request: Request) -> bool:
        admin_id = request.session.get('admin_id')
        if admin_id is None:
            return False

        def active():
            with SessionLocal() as db:
                admin = db.get(AdminModel, admin_id)
                return bool(admin and admin.is_active)

        return await run_in_threadpool(active)


def setup_admin(auth_app: FastAPI):
    admin = SQLAdmin(
        auth_app,
        engine,
        authentication_backend=AdminAuthBackend(
            secret_key=SECRET_KEY,
            max_age=3600,
            same_site='strict',
            https_only=os.getenv('ADMIN_COOKIE_SECURE', 'false').lower() == 'true',
        ),
    )
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
