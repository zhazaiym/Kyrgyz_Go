from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from mysite.api.client_auth import (LoginCredentials, RegistrationCredentials,
                                    create_password_client, current_client, issue_token,
                                    login_client)
from mysite.api.errors import error_detail
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db

router = APIRouter(prefix='/account', tags=['Tourist Account'])


def normalize_email(value: str):
    try:
        result = optional_email(value)
        if result is None:
            raise ValueError('Email is required')
        return result
    except ValueError:
        raise HTTPException(status_code=422, detail=error_detail('validation_error'))


def with_profile(db: Session, client: ChatClient, result: dict):
    profile = db.query(ClientProfile).filter(ClientProfile.client_id == client.id).first()
    result.update(
        {
            'name': profile.name if profile else None,
            'phone': profile.phone if profile else None,
            'email': client.email,
        }
    )
    return result


@router.post('/register', status_code=201)
def register(data: RegistrationCredentials, request: Request, db: Session = Depends(get_db)):
    client = create_password_client(db, request, data)
    return with_profile(db, client, issue_token(db, client))


@router.post('/login')
def login(data: LoginCredentials, request: Request, db: Session = Depends(get_db)):
    client = login_client(db, request, data)
    return with_profile(db, client, issue_token(db, client))


@router.get('/me')
def my_profile(client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    return with_profile(
        db,
        client,
        {'client_id': client.id, 'client_code': f'KG-{client.id:06d}', 'username': client.username},
    )
