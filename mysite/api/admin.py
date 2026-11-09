import os
import secrets
from pathlib import Path
from uuid import UUID

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mysite.api.admin_sessions import (new_session, remember_browser, rotate_refresh, session_live,
                                       token_pair, token_session_id)
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.api.password_work import BoundedPasswords
from mysite.api.rate_limit import enforce_login_attempt
from mysite.api.selection_status import require_status_transition
from mysite.database.admin_security_models import AdminSession, AdminTrustedDevice
from mysite.database.db import get_db
from mysite.database.models import Admin, RequestStatusChoices, TravelRequest
from mysite.database.schemas.admin import AdminLoginSchema, AdminOutSchema, TokenSchema
from mysite.database.schemas.requests import TravelRequestOutSchema
from mysite.database.token_utils import utcnow
from mysite.database.travel_request_queries import list_travel_requests as query_travel_requests

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY')
if (
    not SECRET_KEY
    or len(SECRET_KEY.encode('utf-8')) < 32
    or SECRET_KEY.casefold().startswith('replace-with-')
):
    raise RuntimeError('SECRET_KEY must be a non-placeholder random value of at least 32 bytes')
admin_router = APIRouter(prefix='/admin', tags=['Admin'])

admin_bearer = HTTPBearer(auto_error=False, scheme_name='AdminBearer')
password_hash = BoundedPasswords()
dummy_admin_hash = password_hash.hash(secrets.token_urlsafe(32))

ALGORITHM = 'HS256'


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
    db: Session = Depends(get_db),
) -> Admin:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=error_detail('authentication_required'),
        headers={'WWW-Authenticate': 'Bearer'},
    )

    if credentials is None:
        raise credentials_exception
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], options={'require': ['exp', 'sub', 'sid']}
        )
        admin_id = payload.get('sub')
        if admin_id is None:
            raise credentials_exception
        admin_id = int(admin_id)
        sid = str(UUID(payload.get('sid')))
    except (InvalidTokenError, ValueError, TypeError, AttributeError):
        raise credentials_exception

    result = (
        db.query(Admin, AdminSession)
        .join(AdminSession, AdminSession.admin_id == Admin.id)
        .filter(Admin.id == admin_id, AdminSession.id == sid, Admin.is_active.is_(True))
        .first()
    )
    if result is None or not session_live(result[1]):
        raise credentials_exception
    return result[0]


def require_admin_roles(*roles):
    def dependency(current_admin: Admin = Depends(get_current_admin)):
        if current_admin.role != 'owner' and current_admin.role not in roles:
            raise HTTPException(status_code=403, detail=error_detail('forbidden'))
        return current_admin

    dependency.admin_roles = roles
    return dependency


@admin_router.post('/login/', response_model=TokenSchema, response_model_exclude_none=True)
def login_admin(admin: AdminLoginSchema, request: Request, db: Session = Depends(get_db)):
    found = db.query(Admin).filter(Admin.username == admin.username).first()
    admin_id = found.id if found else None
    account_key = f'admin:{admin_id}' if found else f'unknown:{admin.username.strip().casefold()}'
    encoded = found.hashed_password if found else dummy_admin_hash
    active = bool(found and found.is_active)
    db.rollback()
    enforce_login_attempt('admin-login', request, account_key)
    valid = verify_password(admin.password, encoded)
    invalid = JSONResponse({'code': 'invalid_credentials'}, status_code=401)
    if not admin_id or not valid or not active:
        return invalid
    found = db.get(Admin, admin_id, with_for_update=True, populate_existing=True)
    if not found or not found.is_active or found.hashed_password != encoded:
        return invalid
    row, refresh = new_session(db, found.id, request.headers.get('user-agent', ''))
    result = token_pair(row, refresh)
    if admin.remember_device:
        device, raw = remember_browser(db, found.id, request.headers.get('user-agent', ''))
        result.update(device_token=raw, device_id=device.id)
    db.commit()
    return result


class RefreshInput(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=512)


@admin_router.post('/token/refresh/', response_model=TokenSchema, response_model_exclude_none=True)
def refresh_admin(data: RefreshInput, db: Session = Depends(get_db)):
    result = rotate_refresh(db, data.refresh_token)
    if result is None:
        return JSONResponse({'code': 'session_expired'}, status_code=401)
    return result


@admin_router.post('/logout/', status_code=204)
def logout_admin(data: RefreshInput, db: Session = Depends(get_db)):
    sid = token_session_id(data.refresh_token)
    if sid:
        row = db.get(AdminSession, sid, with_for_update=True)
        if row and row.revoked_at is None:
            row.revoked_at = utcnow()
            db.commit()
    return Response(status_code=204)


def _own_rows(db, model, admin_id):
    return (
        db.query(model)
        .filter(model.admin_id == admin_id)
        .order_by(model.created_at.desc(), model.id)
    )


@admin_router.get('/sessions/')
def list_sessions(
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
    db: Session = Depends(get_db),
):
    return [
        {
            key: getattr(row, key)
            for key in (
                'id',
                'created_at',
                'last_used_at',
                'expires_at',
                'revoked_at',
                'user_agent',
            )
        }
        for row in _own_rows(db, AdminSession, current_admin.id).all()
    ]


@admin_router.get('/devices/')
def list_devices(
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
    db: Session = Depends(get_db),
):
    return [
        {
            key: getattr(row, key)
            for key in ('id', 'label', 'created_at', 'last_used_at', 'expires_at', 'revoked_at')
        }
        for row in _own_rows(db, AdminTrustedDevice, current_admin.id).all()
    ]


def _revoke_own(db, model, identity, admin_id):
    row = db.get(model, identity, with_for_update=True)
    if row is None or row.admin_id != admin_id:
        raise HTTPException(404, detail=error_detail('not_found'))
    row.revoked_at = utcnow()
    db.commit()
    return Response(status_code=204)


@admin_router.delete('/sessions/{identity}/', status_code=204)
def revoke_session(
    identity: UUID,
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
    db: Session = Depends(get_db),
):
    return _revoke_own(db, AdminSession, str(identity), current_admin.id)


@admin_router.delete('/devices/{identity}/', status_code=204)
def revoke_device(
    identity: UUID,
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
    db: Session = Depends(get_db),
):
    return _revoke_own(db, AdminTrustedDevice, str(identity), current_admin.id)


@admin_router.delete('/devices/', status_code=204)
def revoke_devices(
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
    db: Session = Depends(get_db),
):
    db.query(AdminTrustedDevice).filter(
        AdminTrustedDevice.admin_id == current_admin.id, AdminTrustedDevice.revoked_at.is_(None)
    ).update({'revoked_at': utcnow()}, synchronize_session=False)
    db.commit()
    return Response(status_code=204)


@admin_router.get('/me/', response_model=AdminOutSchema)
def get_admin_profile(
    current_admin: Admin = Depends(require_admin_roles('manager', 'catalog_editor')),
):
    return current_admin


class RequestStatusUpdate(BaseModel):
    status: RequestStatusChoices


@admin_router.get('/requests/', response_model=list[TravelRequestOutSchema])
def list_travel_requests(
    current_admin: Admin = Depends(require_admin_roles('manager')),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    return query_travel_requests(db, pagination.offset, pagination.limit)


@admin_router.get('/requests/{request_id}/', response_model=TravelRequestOutSchema)
def get_travel_request(
    request_id: int,
    current_admin: Admin = Depends(require_admin_roles('manager')),
    db: Session = Depends(get_db),
):
    request = db.get(TravelRequest, request_id)
    if request is None:
        raise HTTPException(404, error_detail('not_found'))
    return request


@admin_router.patch('/requests/{request_id}/status/', response_model=TravelRequestOutSchema)
def update_travel_request_status(
    request_id: int,
    data: RequestStatusUpdate,
    current_admin: Admin = Depends(require_admin_roles('manager')),
    db: Session = Depends(get_db),
):
    request = db.get(TravelRequest, request_id, with_for_update=True, populate_existing=True)
    if request is None:
        raise HTTPException(404, error_detail('not_found'))
    require_status_transition(request.status, data.status)
    request.status = data.status
    db.commit()
    db.refresh(request)
    return request
