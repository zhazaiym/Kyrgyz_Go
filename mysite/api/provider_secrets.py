import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _cipher():
    material = hashlib.sha256(b'auth-provider-secret:' + os.environ['SECRET_KEY'].encode())
    return Fernet(base64.urlsafe_b64encode(material.digest()))


def seal_secret(value):
    return _cipher().encrypt(value.encode()).decode()


def open_secret(token):
    if not token:
        return None
    try:
        return _cipher().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
