import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from mysite.database.db import get_db
from mysite.database.chat_models import ChatClient, ChatLoginToken

router = APIRouter(prefix='/chat/auth', tags=['Chat authentication'])
passwords = PasswordHash.recommended()

def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)

def issue_token(db: Session, client: ChatClient):
    raw = secrets.token_urlsafe(40)
    db.add(ChatLoginToken(client_id=client.id, token_hash=digest(raw),
                          expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    db.commit()
    return {'access_token':raw, 'token_type':'bearer', 'client_id':client.id,
            'client_code': f'KG-{client.id:06d}', 'username':client.username}

@router.post('/register', status_code=201)
def register(data: Credentials, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,50}', username):
        raise HTTPException(422, 'Логин: латинские буквы, цифры и _ (3–50 символов)')
    client = ChatClient(username=username, password_hash=passwords.hash(data.password))
    db.add(client)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Этот логин уже занят')
    db.refresh(client)
    return issue_token(db, client)

@router.post('/login')
def login(data: Credentials, db: Session = Depends(get_db)):
    client = db.query(ChatClient).filter(ChatClient.username == data.username.strip().lower()).first()
    if not client or not passwords.verify(data.password, client.password_hash):
        raise HTTPException(401, 'Неправильный логин или пароль')
    return issue_token(db, client)

def client_by_token(db: Session, token: str):
    if not token:
        raise HTTPException(401, 'Требуется вход в чат')
    access = db.query(ChatLoginToken).filter(ChatLoginToken.token_hash == digest(token)).first()
    if not access:
        raise HTTPException(401, 'Недействительный токен входа')
    if access.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, 'Сессия входа истекла. Войдите снова')
    client = db.get(ChatClient, access.client_id)
    if not client:
        raise HTTPException(401, 'Клиент не найден')
    return client

# def current_client(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
#     scheme, _, token = (authorization or '').partition(' ')
#     if scheme.lower() != 'bearer':
#         raise HTTPException(401, 'Требуется Bearer token')
#     return client_by_token(db, token)

security = HTTPBearer()


def current_client(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    return client_by_token(db, credentials.credentials)

@router.get('/me')
def me(client: ChatClient = Depends(current_client)):
    return {'client_id':client.id, 'client_code':f'KG-{client.id:06d}', 'username':client.username}

@router.post('/logout')
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    scheme, _, token = (authorization or '').partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(401, 'Требуется вход')
    access = db.query(ChatLoginToken).filter(ChatLoginToken.token_hash == digest(token)).first()
    if access:
        db.delete(access)
        db.commit()
    return {'ok': True}
