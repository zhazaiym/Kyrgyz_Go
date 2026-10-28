"""Atomic database limits for account actions and chat, shared across workers."""

import hashlib
import os
import time
from collections import OrderedDict
from threading import Lock

from fastapi import HTTPException, Request
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from mysite.api.network_identity import client_network
from mysite.database.db import SessionLocal
from mysite.database.rate_limit_models import RateLimitCounter

_cache_lock = Lock()
_blocked = OrderedDict()
_cleanup_after = 0


def _current_epoch():
    return int(time.time())


def _counter_key(scope, principal):
    return hashlib.sha256(f'{scope}\0{principal}'.encode()).hexdigest()


def consume_rate_limits(limits, *, current_time=None, clear=()):
    instant = _current_epoch() if current_time is None else current_time
    rows, bounds, identities, retries = [], {}, [], []
    for scope, principal, maximum, window in limits:
        if maximum < 1 or window < 1:
            raise ValueError('Rate limits must be positive')
        start = instant // window * window
        key = _counter_key(scope, principal)
        if key in bounds:
            raise ValueError('Duplicate rate-limit identity in a batch')
        bounds[key] = maximum + 1
        identities.append(key)
        retries.append(max(1, start + window - instant))
        rows.append({'key_hash': key, 'window_start': start, 'request_count': 1})
    table = RateLimitCounter.__table__
    with SessionLocal() as db:
        statement = postgresql_insert(table).values(rows)
        ceiling = case(bounds, value=table.c.key_hash, else_=1)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.key_hash],
            set_={
                'window_start': statement.excluded.window_start,
                'request_count': case(
                    (
                        table.c.window_start == statement.excluded.window_start,
                        case(
                            (table.c.request_count < ceiling, table.c.request_count + 1),
                            else_=ceiling,
                        ),
                    ),
                    else_=1,
                ),
            },
        ).returning(table.c.key_hash, table.c.request_count)
        counts = dict(db.execute(statement).all())
        clear_keys = [_counter_key(scope, principal) for scope, principal in clear]
        if clear_keys:
            db.execute(delete(table).where(table.c.key_hash.in_(clear_keys)))
        global _cleanup_after
        with _cache_lock:
            cleanup = instant >= _cleanup_after
            if cleanup:
                _cleanup_after = instant + 60
        if cleanup:
            db.execute(delete(table).where(table.c.window_start < instant - 8 * 86_400))
        db.commit()
    return [(counts[key], retry) for key, retry in zip(identities, retries)]


def consume_rate_limit(scope, principal, *, max_requests, window_seconds, current_time=None):
    return consume_rate_limits(
        [(scope, principal, max_requests, window_seconds)], current_time=current_time
    )[0]


def _limited(retry):
    raise HTTPException(
        429,
        detail={'code': 'rate_limited', 'retry_after': retry},
        headers={'Retry-After': str(retry)},
    )


def enforce_rate_limits(limits):
    if os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() in {'0', 'false', 'no'}:
        return
    instant = _current_epoch()
    with _cache_lock:
        for limit in limits:
            until = _blocked.get(limit, 0)
            if until > instant:
                _limited(until - instant)
            _blocked.pop(limit, None)
    results = consume_rate_limits(limits, current_time=instant)
    rejected = []
    with _cache_lock:
        for limit, (count, retry) in zip(limits, results):
            if count > limit[2]:
                _blocked[limit] = instant + retry
                _blocked.move_to_end(limit)
                rejected.append(retry)
        while len(_blocked) > 4096:
            _blocked.popitem(last=False)
    if rejected:
        _limited(max(rejected))


def enforce_rate_limit(scope, principal, *, max_requests, window_seconds):
    enforce_rate_limits([(scope, principal, max_requests, window_seconds)])


def login_attempt_allowed(
    db, scope, request, account_key, *, ip_limit, account_limit, window_seconds
):
    if os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() in {'0', 'false', 'no'}:
        return True
    instant = _current_epoch()
    address = client_network(request.client.host if request.client else 'unknown')
    failed_principal = f'failed-account:{account_key}'
    trusted_principal = f'{scope}:{account_key}\0ip:{address}'
    trusted_window = 7 * 86_400
    entries = [
        (scope, f'ip:{address}', ip_limit, window_seconds),
        (scope, failed_principal, account_limit, window_seconds),
        ('successful-login', trusted_principal, 1, trusted_window),
    ]
    keys = {
        _counter_key(item_scope, principal): (window, maximum)
        for item_scope, principal, maximum, window in entries
    }
    table = RateLimitCounter.__table__
    rows = db.execute(
        select(table.c.key_hash, table.c.window_start, table.c.request_count).where(
            table.c.key_hash.in_(keys)
        )
    ).all()
    counts = {key: (start, count) for key, start, count in rows}

    def current_count(entry):
        item_scope, principal, _maximum, window = entry
        key = _counter_key(item_scope, principal)
        row = counts.get(key)
        start = instant // window * window
        return row[1] if row and row[0] == start else 0

    ip_count = current_count(entries[0])
    if ip_count >= ip_limit:
        start = instant // window_seconds * window_seconds
        _limited(max(1, start + window_seconds - instant))
    if current_count(entries[1]) < account_limit:
        return True
    trusted = counts.get(_counter_key('successful-login', trusted_principal))
    trusted_start = instant // trusted_window * trusted_window
    return bool(trusted and trusted[0] == trusted_start and trusted[1] > 0)


def record_login_failure(scope, request, account_key, *, ip_limit, account_limit, window_seconds):
    if os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() in {'0', 'false', 'no'}:
        return
    address = client_network(request.client.host if request.client else 'unknown')
    limits = [
        (scope, f'ip:{address}', ip_limit, window_seconds),
        (scope, f'failed-account:{account_key}', account_limit, window_seconds),
    ]
    results = consume_rate_limits(limits)
    rejected = [retry for limit, (count, retry) in zip(limits, results) if count > limit[2]]
    if rejected:
        _limited(max(rejected))


def record_login_success(scope, request, account_key, *, ip_limit, window_seconds):
    if os.getenv('RATE_LIMIT_ENABLED', 'true').strip().casefold() in {'0', 'false', 'no'}:
        return
    address = client_network(request.client.host if request.client else 'unknown')
    consume_rate_limits(
        [
            (scope, f'ip:{address}', ip_limit, window_seconds),
            ('successful-login', f'{scope}:{account_key}\0ip:{address}', 1, 7 * 86_400),
        ],
        clear=[(scope, f'failed-account:{account_key}')],
    )


def enforce_request_limits(
    scope: str,
    request: Request,
    identity: str,
    *,
    ip_limit: int,
    identity_limit: int,
    window_seconds: int,
):
    address = client_network(request.client.host if request.client else 'unknown')
    principal = f'identity:{identity.strip().casefold()}'
    enforce_rate_limits(
        [
            (scope, f'ip:{address}', ip_limit, window_seconds),
            (scope, principal, identity_limit, window_seconds),
        ]
    )


def enforce_chat_message_limits(client_id):
    principal = f'client:{client_id}'
    enforce_rate_limits(
        [('chat-message-minute', principal, 10, 60), ('chat-message-day', principal, 300, 86_400)]
    )
