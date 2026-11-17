"""Atomic database limits for account actions and chat, shared across workers."""

import hashlib
import logging
import time
from collections import OrderedDict
from threading import Lock

from fastapi import HTTPException, Request
from sqlalchemy import case, delete, func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert

from ML.errors import AIError
from mysite.api.network_identity import rate_limits_enabled, request_network
from mysite.api.resource_limits import setting
from mysite.database.db import SessionLocal
from mysite.database.rate_limit_models import RateLimitCounter

log = logging.getLogger(__name__)
_cache_lock = Lock()
_blocked = OrderedDict()
_cleanup_after = 0
LOGIN_LIMITS = {
    'client-login': {'ip': 30, 'account_ip': 8, 'window': 60},
    'admin-login': {'ip': 20, 'account_ip': 5, 'window': 60},
}


def _current_epoch():
    return int(time.time())


def _counter_key(scope, principal):
    return hashlib.sha256(f'{scope}\0{principal}'.encode()).hexdigest()


def _account_index(principal):
    if not principal.startswith('account-ip:'):
        return None
    account_key = principal[len('account-ip:') :].rsplit(':ip:', 1)[0]
    if account_key.startswith('unknown:'):
        identifier = account_key[len('unknown:') :]
        account_key = 'unknown:' + hashlib.sha256(identifier.encode('utf-8')).hexdigest()
    return account_key


def consume_rate_limits(limits, *, current_time=None):
    instant = _current_epoch() if current_time is None else current_time
    rows, bounds, identities, retries = [], {}, [], []
    for scope, principal, maximum, window, *amount in limits:
        # The optional fifth item is how much to add: one request, or a number of tokens.
        amount = amount[0] if amount else 1
        if maximum < 1 or window < 1 or amount < 0:
            raise ValueError('Rate limits must be positive')
        start = instant // window * window
        key = _counter_key(scope, principal)
        if key in bounds:
            raise ValueError('Duplicate rate-limit identity in a batch')
        bounds[key] = maximum + 1
        identities.append(key)
        retries.append(max(1, start + window - instant))
        account_id = _account_index(principal)
        rows.append(
            {
                'key_hash': key,
                'scope': scope,
                'account_id': account_id,
                'window_start': start,
                'request_count': amount,
            }
        )
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
                        func.least(
                            table.c.request_count + statement.excluded.request_count, ceiling
                        ),
                    ),
                    else_=statement.excluded.request_count,
                ),
            },
        ).returning(table.c.key_hash, table.c.request_count)
        counts = dict(db.execute(statement).all())
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
    if not rate_limits_enabled():
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


def enforce_login_attempt(scope, request, account_key):
    """Atomically cap login attempts per IP and account/IP pair; never lock an account."""
    policy = LOGIN_LIMITS[scope]
    address = request_network(request)
    enforce_rate_limits(
        [
            (scope, f'ip:{address}', policy['ip'], policy['window']),
            (
                scope,
                f'account-ip:{account_key}:ip:{address}',
                policy['account_ip'],
                policy['window'],
            ),
        ]
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
    address = request_network(request)
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


AI_BUDGET_WINDOW = 86_400
_budget_signal = (0, 0)  # the day and the level last reported to people


def _ai_budgets(client_id, network):
    """Daily token budgets: the client, their address (all its accounts), everyone."""
    limits = [('ai-tokens', f'client:{client_id}', setting('AI_CLIENT_DAILY_TOKENS'))]
    if network:
        limits.append(('ai-tokens', f'ip:{network}', setting('AI_IP_DAILY_TOKENS')))
    limits.append(('ai-tokens', 'all', setting('AI_DAILY_TOKENS')))
    return [(*limit, AI_BUDGET_WINDOW) for limit in limits]


def enforce_ai_budget(client_id, network=None):
    """Refuse before the model is called once a daily token budget is spent."""
    if not rate_limits_enabled():
        return
    limits = _ai_budgets(client_id, network)
    spent = consume_rate_limits([(*limit, 0) for limit in limits])
    if spent[-1][0] >= limits[-1][2]:
        raise AIError('ai_rate_limit', 'The daily AI token budget is spent')
    for limit, (count, retry) in zip(limits, spent):
        if count >= limit[2]:
            _limited(retry)


def record_ai_spend(client_id, network, tokens):
    """Add what a reply cost to the budgets; tell people when the common one runs out."""
    if tokens <= 0 or not rate_limits_enabled():
        return
    limits = _ai_budgets(client_id, network)
    instant = _current_epoch()
    spent = consume_rate_limits([(*limit, tokens) for limit in limits], current_time=instant)
    used, maximum = spent[-1][0], limits[-1][2]
    level = 2 if used >= maximum else 1 if used * 5 >= maximum * 4 else 0
    signal = (instant // AI_BUDGET_WINDOW, level)
    global _budget_signal
    with _cache_lock:
        report = level and signal > _budget_signal
        if report:
            _budget_signal = signal
    if report and level == 2:
        log.error('AI token budget for today is spent (%d tokens); chat refuses messages', maximum)
    elif report:
        log.warning('AI token budget for today is 80%% spent: %d of %d tokens', used, maximum)
