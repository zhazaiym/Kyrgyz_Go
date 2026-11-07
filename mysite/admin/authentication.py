"""SQLAdmin authentication uses the same revocable sessions as the API."""

import os

from fastapi import HTTPException, Request
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse

from mysite.api.admin import SECRET_KEY, dummy_admin_hash, verify_password
from mysite.api.admin_sessions import (new_session, remember_browser, setting, sql_session_admin,
                                       trusted_device, verify_second_factor)
from mysite.api.rate_limit import enforce_login_attempt
from mysite.database.admin_security_models import AdminSession
from mysite.database.db import SessionLocal
from mysite.database.models import Admin
from mysite.database.token_utils import utcnow

DEVICE_COOKIE = 'kerben_admin_device'


class AdminAuthBackend(AuthenticationBackend):
    def __init__(self):
        super().__init__(
            secret_key=SECRET_KEY,
            max_age=setting('ADMIN_SESSION_HOURS') * 3600,
            same_site='strict',
            https_only=os.getenv('ADMIN_COOKIE_SECURE', 'true').lower() == 'true',
        )

    @staticmethod
    def login_identity(request, username, password, totp_code, remember=False):
        with SessionLocal() as db:
            found = db.query(Admin).filter_by(username=username).first()
            identity = found.id if found else None
            encoded = found.hashed_password if found else dummy_admin_hash
            active = bool(found and found.is_active)
        enforce_login_attempt(
            'admin-login',
            request,
            f'admin:{identity}' if identity else f'unknown:{username.casefold()}',
        )
        valid = verify_password(password, encoded)
        if not identity or not active or not valid:
            return None
        with SessionLocal() as db:
            admin = db.get(Admin, identity, with_for_update=True, populate_existing=True)
            if not admin or not admin.is_active or admin.hashed_password != encoded:
                return None
            accepted, used_code = verify_second_factor(
                db, admin, totp_code, request.cookies.get(DEVICE_COOKIE)
            )
            if not accepted:
                return None
            device_token = None
            if used_code and remember:
                _, device_token = remember_browser(
                    db, identity, request.headers.get('user-agent', '')
                )
            row, _ = new_session(db, identity, request.headers.get('user-agent', ''))
            result = (identity, row.id, row.created_at.timestamp(), device_token)
            db.commit()
            return result

    async def login(self, request: Request):
        form = await request.form()
        username, password = str(form.get('username', '')).strip(), str(form.get('password', ''))
        code = str(form.get('totp_code', ''))
        if not 1 <= len(username) <= 100 or not 1 <= len(password) <= 128 or len(code) > 32:
            return False
        try:
            identity = await run_in_threadpool(
                self.login_identity,
                request,
                username,
                password,
                code,
                form.get('remember_device') in ('on', 'true', '1'),
            )
        except HTTPException as exc:
            if exc.status_code == 429:
                return False
            raise
        if identity is None:
            return False
        admin_id, sid, login_at, device_token = identity
        request.session.clear()
        request.session.update(
            admin_id=admin_id, sid=sid, login_at=login_at, seen_at=int(login_at), admin_mfa=True
        )
        if device_token:
            response = RedirectResponse(request.url_for('admin:index'), status_code=302)
            response.set_cookie(
                DEVICE_COOKIE,
                device_token,
                max_age=min(30, setting('ADMIN_TRUSTED_DEVICE_DAYS')) * 86400,
                httponly=True,
                secure=True,
                samesite='strict',
                path='/admin',
            )
            return response
        return True

    async def logout(self, request: Request):
        def revoke():
            with SessionLocal() as db:
                row = (
                    db.get(AdminSession, request.session.get('sid'))
                    if request.session.get('sid')
                    else None
                )
                if row:
                    row.revoked_at = utcnow()
                    db.commit()

        await run_in_threadpool(revoke)
        request.session.clear()
        return True

    @staticmethod
    def active_admin_role(admin_id):
        with SessionLocal() as db:
            admin = db.get(Admin, admin_id)
            return admin.role if admin and admin.is_active else None

    @staticmethod
    def active_admin(admin_id):
        return AdminAuthBackend.active_admin_role(admin_id) is not None

    async def authenticate(self, request: Request):
        def check():
            with SessionLocal() as db:
                return sql_session_admin(db, request.session, touch=True) is not None

        valid = await run_in_threadpool(check)
        if not valid:
            request.session.clear()
        return valid


async def forget_browser(request):
    if not await AdminAuthBackend().authenticate(request):
        return RedirectResponse(request.url_for('admin:login'), status_code=302)

    def revoke():
        with SessionLocal() as db:
            device = trusted_device(
                db, request.session['admin_id'], request.cookies.get(DEVICE_COOKIE)
            )
            if device:
                device.revoked_at = utcnow()
                db.commit()

    await run_in_threadpool(revoke)
    response = RedirectResponse(request.url_for('admin:index'), status_code=303)
    response.delete_cookie(
        DEVICE_COOKIE, path='/admin', httponly=True, secure=True, samesite='strict'
    )
    return response
