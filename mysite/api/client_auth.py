import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.password_work import BoundedPasswords
from mysite.api.rate_limit import (
    enforce_request_limits,
    login_attempt_allowed,
    record_login_failure,
    record_login_success,
)
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatClient, ChatLoginToken
from mysite.database.db import get_db
from mysite.database.token_utils import digest

router = APIRouter(tags=['Client authentication'])
passwords = BoundedPasswords()
dummy_password_hash = passwords.hash(secrets.token_urlsafe(32))
client_bearer = HTTPBearer(auto_error=False, scheme_name='ClientBearer')


def login_required(message: str) -> HTTPException:
    return HTTPException(
        401,
        detail={
            'code': 'authentication_required',
            'message': message,
            'register_url': '/auth/register',
            'login_url': '/auth/login',
        },
        headers={'WWW-Authenticate': 'Bearer'},
    )


class RegistrationCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr | None = Field(default=None, max_length=254)

    @field_validator('email', mode='after')
    @classmethod
    def normalize_email(cls, value):
        return optional_email(value)


class LoginCredentials(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=254)
    email: str | None = Field(default=None, min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode='after')
    def require_one_identifier(self):
        if (self.username is None) == (self.email is None):
            raise ValueError('Укажите email или логин, но не оба поля одновременно')
        return self


def issue_token(db: Session, client: ChatClient):
    raw = secrets.token_urlsafe(40)
    db.add(
        ChatLoginToken(
            client_id=client.id,
            token_hash=digest(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    )
    db.commit()
    return {
        'access_token': raw,
        'token_type': 'bearer',
        'client_id': client.id,
        'client_code': f'KG-{client.id:06d}',
        'username': client.username,
        'email': client.email,
    }


def authenticate_client(
    db: Session, identifier: str, password: str, *, email_only=False, request: Request | None = None
):
    field = ChatClient.email if email_only or '@' in identifier else ChatClient.username
    with Session(bind=db.get_bind(), autoflush=False) as lookup:
        client = lookup.query(ChatClient).filter(field == identifier).first()
        client_id = client.id if client else None
        account_key = (
            f'client:{client_id}'
            if client_id is not None
            else (f'unknown:{identifier.strip().casefold()}')
        )
        verified_hash = client.password_hash if client else dummy_password_hash
        if request is not None and not login_attempt_allowed(
            lookup,
            'client-login',
            request,
            account_key,
            ip_limit=30,
            account_limit=8,
            window_seconds=60,
        ):
            raise login_required('Неверный email или пароль')
    # Argon2 must not hold a row lock or a pooled connection. Recheck the hash
    # under the short token-issuance lock so a concurrent reset still wins.
    valid = passwords.verify(password, verified_hash)
    if client_id is None or not valid:
        if request is not None:
            record_login_failure(
                'client-login',
                request,
                account_key,
                ip_limit=30,
                account_limit=8,
                window_seconds=60,
            )
        raise login_required('Неверный email или пароль')
    client = db.get(ChatClient, client_id, with_for_update=True, populate_existing=True)
    if client is None or client.password_hash != verified_hash:
        if request is not None:
            record_login_failure(
                'client-login',
                request,
                account_key,
                ip_limit=30,
                account_limit=8,
                window_seconds=60,
            )
        raise login_required('Неверный email или пароль')
    if request is not None:
        record_login_success('client-login', request, account_key, ip_limit=30, window_seconds=60)
    return client


@router.post('/register', status_code=201)
def register(data: RegistrationCredentials, request: Request, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    enforce_request_limits(
        'client-register', request, username, ip_limit=10, identity_limit=3, window_seconds=3600
    )
    if not re.fullmatch(r'[a-z0-9_]{3,50}', username):
        raise HTTPException(422, 'Логин: латинские буквы, цифры и _ (3–50 символов)')
    client = ChatClient(
        username=username, email=data.email, password_hash=passwords.hash(data.password)
    )
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Этот логин или email уже используется')
    db.refresh(client)
    return issue_token(db, client)


@router.post('/login')
def login(data: LoginCredentials, request: Request, db: Session = Depends(get_db)):
    identifier = (data.email if data.email is not None else data.username).strip().lower()
    if data.email is not None or '@' in identifier:
        try:
            identifier = optional_email(identifier)
            if identifier is None:
                raise ValueError('Email is required')
        except ValueError as exc:
            raise HTTPException(422, 'Введите корректный email') from exc
    client = authenticate_client(
        db, identifier, data.password, email_only=data.email is not None, request=request
    )
    return issue_token(db, client)


def client_by_token(db: Session, token: str):
    if not isinstance(token, str) or not 1 <= len(token) <= 256:
        raise login_required('Войдите в аккаунт для доступа к деталям и чату')
    access = db.query(ChatLoginToken).filter(ChatLoginToken.token_hash == digest(token)).first()
    if not access:
        raise login_required('Недействительный токен входа')
    expires = access.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise login_required('Сессия входа истекла. Войдите снова')
    client = db.get(ChatClient, access.client_id)
    if not client:
        raise login_required('Клиент не найден')
    return client


def current_client(
    credentials: HTTPAuthorizationCredentials | None = Depends(client_bearer),
    db: Session = Depends(get_db),
):
    if credentials is None:
        raise login_required('Войдите в аккаунт для доступа к деталям и чату')
    return client_by_token(db, credentials.credentials)


@router.get('/me')
def me(client: ChatClient = Depends(current_client)):
    return {
        'client_id': client.id,
        'client_code': f'KG-{client.id:06d}',
        'username': client.username,
        'email': client.email,
    }


@router.post('/logout')
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    scheme, _, token = (authorization or '').partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise login_required('Требуется вход')
    access = db.query(ChatLoginToken).filter(ChatLoginToken.token_hash == digest(token)).first()
    if access:
        db.delete(access)
        db.commit()
    return {'ok': True}
