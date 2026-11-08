"""Server-side administrator sessions."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, event, inspect, update
from sqlalchemy.orm import Mapped, mapped_column

from mysite.database.db import Base
from mysite.database.token_utils import utcnow


class AdminSession(Base):
    __tablename__ = 'admin_sessions'

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    admin_id: Mapped[int] = mapped_column(ForeignKey('admins.id', ondelete='CASCADE'), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    previous_refresh_hash: Mapped[str | None] = mapped_column(String(64))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(200), default='')


def revoke_admin_access(connection, admin_id):
    now = utcnow()
    connection.execute(
        update(AdminSession)
        .where(AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


@event.listens_for(Base, 'before_update', propagate=True)
def revoke_changed_admin(mapper, connection, target):
    if target.__tablename__ != 'admins':
        return
    state = inspect(target)
    if state.attrs.hashed_password.history.has_changes() or (
        state.attrs.is_active.history.has_changes() and not target.is_active
    ):
        revoke_admin_access(connection, target.id)
