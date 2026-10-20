
import os

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Chat, ChatMessage


chat_router = APIRouter(
    prefix="/chats",
    tags=["Chats"]
)


class MessageInputSchema(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


def check_manager(x_manager_key: str | None = Header(default=None)):
    secret = os.getenv("MANAGER_CHAT_KEY")

    if not secret or x_manager_key != secret:
        raise HTTPException(
            status_code=403,
            detail="Менеджерге уруксат жок"
        )


def get_client_chat(chat_id: int, token: str, db: Session):
    chat = db.get(Chat, chat_id)

    if chat is None or chat.client_token != token:
        raise HTTPException(
            status_code=403,
            detail="Чатка уруксат жок"
        )

    return chat


def serialize_message(message):
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "sender": message.sender,
        "text": message.text,
        "created_at": message.created_at
    }


@chat_router.get("/manager/", dependencies=[Depends(check_manager)])
def manager_chats(db: Session = Depends(get_db)):
    chats = db.query(Chat).order_by(Chat.id.desc()).all()

    return [
        {
            "chat_id": chat.id,
            "booking_id": chat.booking_id,
            "created_at": chat.created_at
        }
        for chat in chats
    ]


@chat_router.get("/{chat_id}/messages/")
def client_messages(
    chat_id: int,
    token: str = Header(alias="X-Chat-Token"),
    db: Session = Depends(get_db)
):
    get_client_chat(chat_id, token, db)

    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.id).all()

    return [serialize_message(m) for m in messages]


@chat_router.post("/{chat_id}/messages/")
def client_send_message(
    chat_id: int,
    data: MessageInputSchema,
    token: str = Header(alias="X-Chat-Token"),
    db: Session = Depends(get_db)
):
    get_client_chat(chat_id, token, db)

    message = ChatMessage(
        chat_id=chat_id,
        sender="client",
        text=data.text
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return serialize_message(message)


@chat_router.get(
    "/manager/{chat_id}/messages/",
    dependencies=[Depends(check_manager)]
)
def manager_messages(
    chat_id: int,
    db: Session = Depends(get_db)
):
    if db.get(Chat, chat_id) is None:
        raise HTTPException(status_code=404, detail="Чат жок")

    messages = db.query(ChatMessage).filter(
        ChatMessage.chat_id == chat_id
    ).order_by(ChatMessage.id).all()

    return [serialize_message(m) for m in messages]


@chat_router.post(
    "/manager/{chat_id}/messages/",
    dependencies=[Depends(check_manager)]
)
def manager_send_message(
    chat_id: int,
    data: MessageInputSchema,
    db: Session = Depends(get_db)
):
    if db.get(Chat, chat_id) is None:
        raise HTTPException(status_code=404, detail="Чат жок")

    message = ChatMessage(
        chat_id=chat_id,
        sender="manager",
        text=data.text
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return serialize_message(message)
