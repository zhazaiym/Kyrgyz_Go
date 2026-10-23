from .views import (AdminAdmin, AboutAdmin, AboutSectionAdmin,
                    TourCategoryAdmin, TourAdmin, TourImageAdmin,
                    TourProgramAdmin, RegionAdmin, DistrictAdmin,
                    HotelAdmin, HotelImageAdmin, TransportAdmin,
                    TransportImageAdmin, HelicopterTourAdmin, HelicopterImageAdmin,
                    TrekkingAdmin, TrekkingImageAdmin, TrekkingProgramAdmin,
                    ContactAdmin, FAQAdmin, ChatRequestAdmin)

from fastapi import FastAPI, Request
from sqladmin import Admin as SQLAdmin
from sqladmin.authentication import AuthenticationBackend

from mysite.api.admin import SECRET_KEY, verify_password
from mysite.database.db import SessionLocal, engine
from mysite.database.models import Admin as AdminModel


class AdminAuthBackend(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))

        with SessionLocal() as db:
            admin = db.query(AdminModel).filter(AdminModel.username == username).first()
            if admin is None or not admin.is_active:
                return False
            if not verify_password(password, admin.hashed_password):
                return False
            request.session["admin_id"] = admin.id
            return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        admin_id = request.session.get("admin_id")
        if admin_id is None:
            return False

        with SessionLocal() as db:
            admin = db.get(AdminModel, admin_id)
            return bool(admin and admin.is_active)

def setup_admin(auth_app: FastAPI):
    admin = SQLAdmin(
        auth_app,
        engine,
        authentication_backend=AdminAuthBackend(secret_key=SECRET_KEY),
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

