from datetime import datetime, timezone

from sqlalchemy import (JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
                        func)
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class ChatClient(Base):
    __tablename__ = 'chat_clients'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index('uq_chat_clients_email_lower', func.lower(email), unique=True),)


class ChatLoginToken(Base):
    __tablename__ = 'chat_login_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('chat_clients.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey('chat_clients.id'), index=True, nullable=False
    )
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default='0', nullable=False
    )
    stage: Mapped[str] = mapped_column(String(30), default='consultation', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey('chat_sessions.id'), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatBookingLink(Base):
    __tablename__ = 'chat_booking_links'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey('chat_clients.id'), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('chat_sessions.id'), index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey('travel_requests.id'), unique=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('session_id', 'revision', name='uq_chat_booking_revision'),)
