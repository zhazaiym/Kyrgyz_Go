from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mysite.api.client_auth import (LoginCredentials, RegistrationCredentials,
                                    create_password_client, current_client, issue_token,
                                    login_client, passwords)
from mysite.api.errors import error_detail
from mysite.api.rate_limit import enforce_login_attempt
from mysite.database.chat_models import ChatClient, ChatLoginToken
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db

router = APIRouter(prefix='/account', tags=['Tourist Account'])


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


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@router.post('/password')
def change_password(
    data: PasswordChange,
    request: Request,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
):
    """Change the caller's password; every other device is signed out, this one gets a new token."""
    enforce_login_attempt('client-login', request, f'client:{client.id}')
    client_id, encoded = client.id, client.password_hash
    db.rollback()
    if not passwords.verify(data.current_password, encoded):
        raise HTTPException(401, error_detail('invalid_credentials'))
    if data.new_password == data.current_password:
        raise HTTPException(422, error_detail('validation_error'))
    new_hash = passwords.hash(data.new_password)
    locked = db.get(ChatClient, client_id, with_for_update=True, populate_existing=True)
    if locked is None or locked.password_hash != encoded:
        raise HTTPException(401, error_detail('invalid_credentials'))
    locked.password_hash = new_hash
    db.query(ChatLoginToken).filter(ChatLoginToken.client_id == client_id).delete(
        synchronize_session=False
    )
    db.commit()
    return issue_token(db, locked)


@router.post('/logout-all', status_code=204)
def logout_everywhere(client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    """Revoke every login token of the caller, including the one used for this request."""
    db.query(ChatLoginToken).filter(ChatLoginToken.client_id == client.id).delete(
        synchronize_session=False
    )
    db.commit()
    return Response(status_code=204)
