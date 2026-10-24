"""Database-backed fixed-window limits shared by every application worker."""
import hashlib
import os
import time

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from mysite.database.db import SessionLocal
from mysite.database.rate_limit_models import RateLimitCounter


def _current_epoch() -> int:
    return int(time.time())


def consume_rate_limit(
    scope: str,
    principal: str,
    *,
    max_requests: int,
    window_seconds: int,
    current_time: int | None = None,
) -> tuple[int, int]:
    """Atomically record a request and return its count and retry delay."""
    instant = _current_epoch() if current_time is None else current_time
    window_start = instant // window_seconds * window_seconds
    key_hash = hashlib.sha256(
        f"{scope}\0{principal}".encode("utf-8")
    ).hexdigest()
    table = RateLimitCounter.__table__

    with SessionLocal() as db:
        dialect = db.bind.dialect.name
        if dialect == "postgresql":
            insert = postgresql_insert
        elif dialect == "sqlite":
            insert = sqlite_insert
        else:
            raise RuntimeError(f"Unsupported database for rate limiting: {dialect}")

        statement = insert(table).values(
            key_hash=key_hash,
            window_start=window_start,
            request_count=1,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.key_hash],
            set_={
                "window_start": window_start,
                "request_count": case(
                    (table.c.window_start == window_start,
                     table.c.request_count + 1),
                    else_=1,
                ),
            },
        ).returning(table.c.request_count)

        request_count = db.execute(statement).scalar_one()
        db.execute(
            delete(table).where(
                table.c.window_start < instant - 86_400
            )
        )
        db.commit()

    retry_after = max(1, window_start + window_seconds - instant)
    return request_count, retry_after


def enforce_rate_limit(
    scope: str,
    principal: str,
    *,
    max_requests: int,
    window_seconds: int,
) -> None:
    if os.getenv("RATE_LIMIT_ENABLED", "true").strip().casefold() in {
        "0", "false", "no",
    }:
        return

    request_count, retry_after = consume_rate_limit(
        scope,
        principal,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    if request_count > max_requests:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def enforce_request_limits(
    scope: str,
    request: Request,
    identity: str,
    *,
    ip_limit: int,
    identity_limit: int,
    window_seconds: int,
) -> None:
    ip_address = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        scope,
        f"ip:{ip_address}",
        max_requests=ip_limit,
        window_seconds=window_seconds,
    )
    enforce_rate_limit(
        scope,
        f"identity:{identity.strip().casefold()}",
        max_requests=identity_limit,
        window_seconds=window_seconds,
    )


def enforce_chat_message_limits(client_id: int) -> None:
    principal = f"client:{client_id}"
    enforce_rate_limit(
        "chat-message-minute", principal,
        max_requests=10, window_seconds=60,
    )
    enforce_rate_limit(
        "chat-message-day", principal,
        max_requests=300, window_seconds=86_400,
    )
