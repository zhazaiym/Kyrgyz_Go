import hashlib
from datetime import datetime, timezone


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)
