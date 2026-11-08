"""Shared session lifecycle for the API and SQLAdmin.

Refresh tokens contain an authenticated session identifier. Rotation is a keyed
derivation from the previous secret and rotation time, allowing a second worker
to reproduce the response during the grace period while storing only hashes.
"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import timedelta, timezone
from uuid import uuid4

import jwt

from mysite.database.admin_security_models import AdminSession
from mysite.database.models import Admin
from mysite.database.token_utils import digest, utcnow


def setting(name):
    defaults = {
        'ADMIN_ACCESS_TOKEN_MINUTES': 60,
        'ADMIN_REFRESH_DAYS': 30,
        'ADMIN_SESSION_HOURS': 168,
    }
    value = int(os.getenv(name, str(defaults[name])))
    if not 1 <= value <= 10000:
        raise RuntimeError(f'{name} must be between 1 and 10000')
    return value


def _key():
    from mysite.api.admin import SECRET_KEY

    return SECRET_KEY.encode()


def _mac(value):
    return (
        base64.urlsafe_b64encode(hmac.new(_key(), value.encode(), hashlib.sha256).digest())
        .decode()
        .rstrip('=')
    )


def _token(sid, secret):
    payload = f'{sid}.{secret}'
    return f'{payload}.{_mac("refresh:" + payload)}'


def token_session_id(token):
    try:
        sid, secret, signature = token.split('.')
        if len(sid) != 36 or not 40 <= len(secret) <= 64:
            return None
        if hmac.compare_digest(signature, _mac(f'refresh:{sid}.{secret}')):
            return sid
    except (ValueError, AttributeError, TypeError):
        pass
    return None


def session_live(row, now=None):
    return bool(row and row.revoked_at is None and row.expires_at > (now or utcnow()))


def new_session(db, admin_id, user_agent=''):
    now = utcnow()
    sid = str(uuid4())
    raw = _token(sid, secrets.token_urlsafe(32))
    row = AdminSession(
        id=sid,
        admin_id=admin_id,
        refresh_hash=digest(raw),
        created_at=now,
        last_used_at=now,
        rotated_at=now,
        expires_at=now + timedelta(days=min(setting('ADMIN_REFRESH_DAYS'), 90)),
        user_agent=user_agent[:200],
    )
    db.add(row)
    return row, raw


def token_pair(row, raw):
    issued = row.rotated_at or row.created_at
    expires = issued + timedelta(minutes=setting('ADMIN_ACCESS_TOKEN_MINUTES'))
    access = jwt.encode(
        {
            'sub': str(row.admin_id),
            'sid': row.id,
            'iat': int(issued.timestamp()),
            'exp': int(expires.timestamp()),
        },
        _key(),
        algorithm='HS256',
    )
    return {
        'access_token': access,
        'token_type': 'bearer',
        'expires_in': setting('ADMIN_ACCESS_TOKEN_MINUTES') * 60,
        'refresh_token': raw,
        'refresh_expires_at': row.expires_at.astimezone(timezone.utc),
    }


def _rotated_token(old, row):
    secret = _mac(f'rotate:{old}:{row.rotated_at.astimezone(timezone.utc).isoformat()}')
    return _token(row.id, secret)


def rotate_refresh(db, raw):
    sid = token_session_id(raw)
    if sid is None:
        return None
    row = db.get(AdminSession, sid, with_for_update=True, populate_existing=True)
    now = utcnow()
    if not session_live(row, now):
        return None
    admin = db.get(Admin, row.admin_id)
    if admin is None or not admin.is_active:
        return None
    supplied = digest(raw)
    if hmac.compare_digest(supplied, row.refresh_hash):
        row.previous_refresh_hash = supplied
        row.rotated_at = now
        row.last_used_at = now
        row.expires_at = min(
            now + timedelta(days=setting('ADMIN_REFRESH_DAYS')), row.created_at + timedelta(days=90)
        )
        new = _rotated_token(raw, row)
        row.refresh_hash = digest(new)
        result = token_pair(row, new)
    elif (
        row.previous_refresh_hash
        and hmac.compare_digest(supplied, row.previous_refresh_hash)
        and row.rotated_at
        and now <= row.rotated_at + timedelta(seconds=30)
    ):
        result = token_pair(row, _rotated_token(raw, row))
    else:
        # The token signature proves that this is a previously issued secret,
        # so arbitrary requests cannot revoke someone else's session.
        row.revoked_at = now
        result = None
    db.commit()
    return result


def sql_session_admin(db, session, *, touch=False):
    now = utcnow()
    sid = session.get('sid')
    if not isinstance(sid, str):
        return None
    row = db.get(AdminSession, sid, with_for_update=touch, populate_existing=True)
    if (
        not session_live(row, now)
        or row.admin_id != session.get('admin_id')
        or now >= row.created_at + timedelta(days=30)
        or now >= row.last_used_at + timedelta(hours=setting('ADMIN_SESSION_HOURS'))
    ):
        return None
    admin = db.get(Admin, row.admin_id)
    if admin is None or not admin.is_active:
        return None
    if touch and now >= row.last_used_at + timedelta(minutes=10):
        row.last_used_at = now
        row.expires_at = min(now + timedelta(days=30), row.created_at + timedelta(days=30))
        session['seen_at'] = int(now.timestamp())
        db.commit()
    return admin
