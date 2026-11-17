"""Revocable server-side sessions of the admin panel."""

from datetime import timedelta
from uuid import uuid4

from mysite.database.admin_security_models import AdminSession
from mysite.database.models import Admin
from mysite.database.token_utils import utcnow
from mysite.settings import number


def setting(name):
    return number(name)


def session_live(row, now=None):
    return bool(row and row.revoked_at is None and row.expires_at > (now or utcnow()))


def new_session(db, admin_id, user_agent=''):
    now = utcnow()
    row = AdminSession(
        id=str(uuid4()),
        admin_id=admin_id,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=30),
        user_agent=user_agent[:200],
    )
    db.add(row)
    return row


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
