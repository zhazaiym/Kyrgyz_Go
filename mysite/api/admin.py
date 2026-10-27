import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mysite.api.password_work import BoundedPasswords
from mysite.api.rate_limit import enforce_request_limits
from mysite.database.db import get_db
from mysite.database.models import Admin, RequestStatusChoices, TravelRequest
from mysite.database.schema import (AdminLoginSchema, AdminOutSchema, TokenSchema,
                                    TravelRequestOutSchema)

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
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(admin_bearer),
    db: Session = Depends(get_db),
) -> Admin:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Токен жараксыз же мөөнөтү бүткөн',
        headers={'WWW-Authenticate': 'Bearer'},
    )

    if credentials is None:
        raise credentials_exception
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], options={'require': ['exp', 'sub']}
        )
        admin_id = payload.get('sub')
        if admin_id is None:
            raise credentials_exception
        admin_id = int(admin_id)
    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    admin_db = db.get(Admin, admin_id)
    if admin_db is None or not admin_db.is_active:
        raise credentials_exception
    return admin_db


@admin_router.post('/login/', response_model=TokenSchema)
def login_admin(admin: AdminLoginSchema, request: Request, db: Session = Depends(get_db)):
    enforce_request_limits(
        'admin-login', request, admin.username, ip_limit=20, identity_limit=5, window_seconds=60
    )
    admin_db = db.query(Admin).filter(Admin.username == admin.username).first()

    valid = verify_password(
        admin.password, admin_db.hashed_password if admin_db else dummy_admin_hash
    )
    if admin_db is None or not valid:
        raise HTTPException(status_code=401, detail='Логин же пароль туура эмес')

    if not admin_db.is_active:
        raise HTTPException(status_code=403, detail='Админ активдүү эмес')

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode({'sub': str(admin_db.id), 'exp': expire}, SECRET_KEY, algorithm=ALGORITHM)
    return {'access_token': token, 'token_type': 'bearer'}


@admin_router.get('/me/', response_model=AdminOutSchema)
def get_admin_profile(current_admin: Admin = Depends(get_current_admin)):
    return current_admin


class RequestStatusUpdate(BaseModel):
    status: RequestStatusChoices


@admin_router.get('/requests/', response_model=list[TravelRequestOutSchema])
def list_travel_requests(
    current_admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)
):
    return db.query(TravelRequest).order_by(TravelRequest.created_at.desc()).limit(100).all()


@admin_router.get('/requests/{request_id}/', response_model=TravelRequestOutSchema)
def get_travel_request(
    request_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    request = db.get(TravelRequest, request_id)
    if request is None:
        raise HTTPException(404, 'Заявка не найдена')
    return request


@admin_router.patch('/requests/{request_id}/status/', response_model=TravelRequestOutSchema)
def update_travel_request_status(
    request_id: int,
    data: RequestStatusUpdate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    request = db.get(TravelRequest, request_id)
    if request is None:
        raise HTTPException(404, 'Заявка не найдена')
    request.status = data.status
    db.commit()
    db.refresh(request)
    return request
