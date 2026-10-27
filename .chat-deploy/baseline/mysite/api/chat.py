"""HTTP chat and booking routes; WebSocket is registered separately in chat_ws.py."""
import uuid
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from mysite.database import db as database
from mysite.database.db import get_db
from mysite.database.chat_models import ChatClient, ChatSession, ChatMessage
from mysite.api.client_auth import client_by_token, current_client, login_required
from mysite.api.chat_service import (
    build_preview,
    confirm_booking_serialized,
    owned,
)
from mysite.chain.prompts import WELCOME_MESSAGE

chat_router = APIRouter(tags=['KYRGYZGO AI Chat'])

class BookingAction(BaseModel):
    session_id: str

class BookingConfirm(BookingAction):
    revision: int
    confirmed: bool


def detached_client_identity(
    authorization: str | None = Header(default=None),
) -> tuple[int, str]:
    scheme, _, token = (authorization or '').partition(' ')
    if scheme.casefold() != 'bearer' or not token:
        raise login_required('Требуется вход')
    with database.SessionLocal() as db:
        return client_by_token(db, token).id, token

@chat_router.post('/chat/session')
def create_session(client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    sid = str(uuid.uuid4())
    db.add(ChatSession(id=sid, client_id=client.id, state={}, revision=0))
    # Persist the parent first; the models have no ORM relationship to order inserts.
    db.flush()
    db.add(ChatMessage(session_id=sid, role='assistant', content=WELCOME_MESSAGE))
    db.commit()
    return {'session_id': sid, 'welcome': WELCOME_MESSAGE}

@chat_router.get('/chat/sessions')
def sessions(client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    rows = db.query(ChatSession).filter(ChatSession.client_id == client.id).order_by(ChatSession.created_at.desc()).limit(50).all()
    return [{'session_id': x.id, 'created_at': x.created_at.isoformat(), 'stage': x.stage} for x in rows]

@chat_router.get('/chat/history/{session_id}')
def history(session_id: str, client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    owned(db, session_id, client.id)
    rows = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.id.desc()).limit(500).all()
    rows.reverse()
    return [{'role': x.role, 'content': x.content, 'created_at': x.created_at.isoformat()} for x in rows]

@chat_router.post('/booking/preview')
def preview(data: BookingAction, client: ChatClient = Depends(current_client), db: Session = Depends(get_db)):
    return build_preview(db, owned(db, data.session_id, client.id))

@chat_router.post('/booking/confirm')
async def confirm(
    data: BookingConfirm,
    identity: tuple[int, str] = Depends(detached_client_identity),
):
    client_id, token = identity
    return await confirm_booking_serialized(
        data.session_id, client_id, token, data.revision, data.confirmed
    )
