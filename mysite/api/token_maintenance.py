"""Bounded expiry cleanup; active tokens are never revoked by housekeeping."""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import SQLAlchemyError

from mysite.database.chat_models import ChatBookingLink, ChatLoginToken, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.selection_models import TravelSelection
from mysite.database.token_utils import utcnow

logger = logging.getLogger(__name__)


def cleanup_expired_tokens(batch_size=1000):
    cutoff = utcnow() - timedelta(days=1)
    counts = {}
    for entity in (ChatLoginToken,):
        counts[entity.__tablename__] = 0
        while True:
            with SessionLocal() as db:
                expired = (
                    select(entity.id)
                    .where(entity.expires_at < cutoff)
                    .order_by(entity.expires_at)
                    .limit(batch_size)
                )
                result = db.execute(delete(entity).where(entity.id.in_(expired)))
                deleted = result.rowcount or 0
                db.commit()
            counts[entity.__tablename__] += deleted
            if deleted < batch_size:
                break
    return counts


CHAT_RETENTION = timedelta(days=365)


def cleanup_old_chats(batch_size=500):
    """Delete chats silent for a year; a chat behind a request or a selection stays with it."""
    cutoff = utcnow() - CHAT_RETENTION
    last_message = (
        select(func.max(ChatMessage.created_at))
        .where(ChatMessage.session_id == ChatSession.id)
        .correlate(ChatSession)
        .scalar_subquery()
    )
    stale = (
        select(ChatSession.id)
        .where(
            ChatSession.created_at < cutoff,
            func.coalesce(last_message, ChatSession.created_at) < cutoff,
            ~exists().where(ChatBookingLink.session_id == ChatSession.id),
            ~exists().where(TravelSelection.session_id == ChatSession.id),
        )
        .order_by(ChatSession.created_at)
        .limit(batch_size)
    )
    removed = 0
    while True:
        with SessionLocal() as db:
            identities = list(db.scalars(stale))
            if identities:
                db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(identities)))
                db.execute(delete(ChatSession).where(ChatSession.id.in_(identities)))
                db.commit()
        removed += len(identities)
        if len(identities) < batch_size:
            return removed


async def token_cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_tokens)
            await asyncio.to_thread(cleanup_old_chats)
        except SQLAlchemyError:
            logger.exception('Token and chat cleanup failed; will retry next hour')
        await asyncio.sleep(3600)
