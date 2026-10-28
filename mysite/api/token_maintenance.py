"""Bounded expiry cleanup; active tokens are never revoked by housekeeping."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from mysite.database.chat_models import ChatLoginToken
from mysite.database.db import SessionLocal
from mysite.database.password_reset_models import PasswordResetToken

logger = logging.getLogger(__name__)


def cleanup_expired_tokens(batch_size=1000):
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    counts = {}
    for entity in (ChatLoginToken, PasswordResetToken):
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


async def token_cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_tokens)
        except SQLAlchemyError:
            logger.exception('Token expiry cleanup failed; will retry next hour')
        await asyncio.sleep(3600)
