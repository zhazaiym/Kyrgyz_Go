"""Secrets of the admin panel: the cookie signing key and administrator passwords."""

import os
import secrets

from mysite.api.password_work import BoundedPasswords

SECRET_KEY = os.getenv('SECRET_KEY')
if (
    not SECRET_KEY
    or len(SECRET_KEY.encode('utf-8')) < 32
    or SECRET_KEY.casefold().startswith('replace-with-')
):
    raise RuntimeError('SECRET_KEY must be a non-placeholder random value of at least 32 bytes')

password_hash = BoundedPasswords()
dummy_admin_hash = password_hash.hash(secrets.token_urlsafe(32))


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)
