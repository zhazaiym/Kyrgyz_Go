import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.client_auth import authenticate_client, current_client, issue_token
from mysite.api.password_work import BoundedPasswords
from mysite.api.rate_limit import enforce_request_limits
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db

router = APIRouter(prefix='/account', tags=['Tourist Account'])

passwords = BoundedPasswords()


class RegisterInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=25)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def normalize_email(value: str):
    try:
        result = optional_email(value)
        if result is None:
            raise ValueError('Email is required')
        return result

    except ValueError:
        raise HTTPException(status_code=422, detail='Введите корректный email')


@router.post('/register', status_code=201)
def register(data: RegisterInput, request: Request, db: Session = Depends(get_db)):
    name = data.name.strip()
    email = normalize_email(data.email)
    enforce_request_limits(
        'client-register', request, email, ip_limit=10, identity_limit=3, window_seconds=3600
    )

    phone = re.sub(r'[\s()\-]', '', data.phone.strip())

    if not name:
        raise HTTPException(422, 'Укажите имя')

    if not re.fullmatch(r'\+?[0-9]{7,15}', phone):
        raise HTTPException(422, 'Введите корректный номер телефона')

    existing = db.query(ChatClient).filter(ChatClient.email == email).first()

    if existing:
        raise HTTPException(409, 'Этот email уже зарегистрирован')

    username = 'u_' + secrets.token_hex(16)

    client = ChatClient(username=username, email=email, password_hash=passwords.hash(data.password))

    db.add(client)

    try:
        db.flush()

        profile = ClientProfile(client_id=client.id, name=name, phone=phone)

        db.add(profile)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Этот email уже зарегистрирован')

    db.refresh(client)

    result = issue_token(db, client)

    result.update({'name': name, 'phone': phone, 'email': email})

    return result


@router.post('/login')
def login(data: LoginInput, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(data.email)
    enforce_request_limits(
        'client-login', request, email, ip_limit=30, identity_limit=8, window_seconds=60
    )

    client = authenticate_client(db, email, data.password, email_only=True)
    profile = db.query(ClientProfile).filter(ClientProfile.client_id == client.id).first()

    result = issue_token(db, client)

    result.update(
        {
            'name': profile.name if profile else None,
            'phone': profile.phone if profile else None,
            'email': client.email,
        }
    )

    return result


@router.get('/me')
def my_profile(client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    profile = db.query(ClientProfile).filter(ClientProfile.client_id == client.id).first()

    return {
        'client_id': client.id,
        'client_code': f'KG-{client.id:06d}',
        'username': client.username,
        'name': profile.name if profile else None,
        'phone': profile.phone if profile else None,
        'email': client.email,
    }
