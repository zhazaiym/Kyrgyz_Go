from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base
from mysite.database.token_utils import utcnow


class AuthProvider(Base):
    __tablename__ = 'auth_providers'

    provider: Mapped[str] = mapped_column(String(20), primary_key=True)
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    app_id: Mapped[str | None] = mapped_column(String(255))
    client_secret: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default='false', nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=utcnow)


class ClientIdentity(Base):
    __tablename__ = 'client_identities'
    __table_args__ = (
        UniqueConstraint('provider', 'subject', name='uq_client_identities_provider_subject'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey('chat_clients.id', ondelete='CASCADE'), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class OAuthState(Base):
    __tablename__ = 'oauth_states'

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    code_verifier: Mapped[str | None] = mapped_column(String(128))
    return_to: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SocialLoginCode(Base):
    __tablename__ = 'social_login_codes'

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey('chat_clients.id', ondelete='CASCADE'), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
