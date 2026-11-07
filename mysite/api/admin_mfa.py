"""TOTP and recovery-code primitives for administrator authentication."""

import base64
import hashlib
import hmac
import secrets
import struct
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _encryption_key(secret_key: str) -> bytes:
    return hmac.new(secret_key.encode(), b'kerben-admin-totp-v1', hashlib.sha256).digest()


def encrypt_totp_secret(secret: str, secret_key: str) -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_encryption_key(secret_key)).encrypt(nonce, secret.encode(), None)
    return base64.urlsafe_b64encode(nonce + encrypted).decode()


def decrypt_totp_secret(ciphertext: str, secret_key: str) -> str:
    raw = base64.urlsafe_b64decode(ciphertext.encode())
    return AESGCM(_encryption_key(secret_key)).decrypt(raw[:12], raw[12:], None).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def totp_code(secret: str, timestamp: int | None = None) -> str:
    timestamp = int(time.time()) if timestamp is None else timestamp
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack('>Q', timestamp // 30), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f'{number % 1_000_000:06d}'


def totp_step(timestamp: int | None = None) -> int:
    timestamp = int(time.time()) if timestamp is None else timestamp
    return timestamp // 30


def verify_totp(secret: str, code: str, timestamp: int | None = None) -> bool:
    return matching_totp_step(secret, code, timestamp) is not None


def matching_totp_step(secret: str, code: str, timestamp: int | None = None) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    timestamp = int(time.time()) if timestamp is None else timestamp
    return next(
        (
            step
            for step in (totp_step(timestamp) - 1, totp_step(timestamp), totp_step(timestamp) + 1)
            if hmac.compare_digest(totp_code(secret, step * 30), code)
        ),
        None,
    )


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_urlsafe(24) for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().casefold().encode()).hexdigest()


def consume_admin_mfa(admin, code: str, secret_key: str) -> bool:
    """Verify TOTP or atomically consume a one-time recovery code."""
    if not admin.totp_secret_encrypted:
        return False
    try:
        secret = decrypt_totp_secret(admin.totp_secret_encrypted, secret_key)
    except (InvalidTag, ValueError, TypeError):
        return False
    matched_step = matching_totp_step(secret, code)
    last_step = getattr(admin, 'totp_last_used_step', None)
    if matched_step is not None:
        if last_step is not None and matched_step <= last_step:
            return False
        admin.totp_last_used_step = matched_step
        return True
    supplied_hash = hash_recovery_code(code)
    hashes = list(admin.recovery_code_hashes or [])
    match = next((stored for stored in hashes if hmac.compare_digest(stored, supplied_hash)), None)
    if match is None:
        return False
    hashes.remove(match)
    admin.recovery_code_hashes = hashes
    return True
