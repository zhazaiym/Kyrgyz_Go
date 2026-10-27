"""Bound memory-hard password work independently of HTTP request concurrency."""

from contextlib import contextmanager
from threading import Lock

from fastapi import HTTPException
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from mysite.api.resource_limits import setting

_lock = Lock()
_active = 0


@contextmanager
def password_capacity():
    global _active
    with _lock:
        if _active >= setting('AUTH_MAX_CONCURRENT', 4, 16):
            raise HTTPException(
                503, 'Authentication is busy; retry shortly', headers={'Retry-After': '2'}
            )
        _active += 1
    try:
        yield
    finally:
        with _lock:
            _active -= 1


class BoundedPasswords:
    def __init__(self):
        self.hasher = PasswordHash.recommended()

    def hash(self, password):
        with password_capacity():
            return self.hasher.hash(password)

    def verify(self, password, encoded):
        with password_capacity():
            try:
                return self.hasher.verify(password, encoded)
            except UnknownHashError:
                return False
