
import os
import hashlib
import secrets
import smtplib
import ssl
import logging

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.chat_models import ChatClient, ChatLoginToken
from mysite.database.client_profile import ClientProfile
from mysite.database.password_reset_models import PasswordResetToken
from mysite.api.registration import normalize_email
from mysite.api.rate_limit import enforce_request_limits


router = APIRouter(
    prefix="/account",
    tags=["Tourist Account"]
)

passwords = PasswordHash.recommended()
logger = logging.getLogger(__name__)


class ForgotPasswordInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class ResetPasswordInput(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def send_reset_email(email: str, token: str):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM")
    frontend_url = os.getenv("FRONTEND_RESET_URL")

    if not host or not sender or not frontend_url:
        raise RuntimeError("SMTP не настроен")

    separator = "&" if "?" in frontend_url else "?"
    link = frontend_url + separator + urlencode({"token": token})

    message = EmailMessage()
    message["Subject"] = "KyrgyzGo - Восстановление пароля"
    message["From"] = sender
    message["To"] = email

    message.set_content(
        "Здравствуйте!\n\n"
        "Для восстановления пароля перейдите по ссылке:\n"
        f"{link}\n\n"
        "Ссылка действует 15 минут.\n"
        "Если вы не запрашивали восстановление пароля, "
        "проигнорируйте это письмо."
    )

    if port == 465:
        with smtplib.SMTP_SSL(
            host,
            port,
            context=ssl.create_default_context(),
            timeout=15
        ) as server:
            if username and password:
                server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=ssl.create_default_context())
            if username and password:
                server.login(username, password)
            server.send_message(message)


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordInput,
    request: Request,
    db: Session = Depends(get_db)
):
    email = normalize_email(data.email)
    enforce_request_limits(
        "password-reset", request, email,
        ip_limit=10, identity_limit=5, window_seconds=3600,
    )

    response = {
        "message": (
            "Если email зарегистрирован, "
            "письмо с инструкцией будет отправлено"
        )
    }

    profile = db.query(ClientProfile).filter(
        ClientProfile.email == email
    ).first()

    if not profile:
        return response

    raw_token = secrets.token_urlsafe(40)

    reset = PasswordResetToken(
        client_id=profile.client_id,
        token_hash=digest(raw_token),
        expires_at=now() + timedelta(minutes=15)
    )

    db.add(reset)
    db.commit()

    try:
        send_reset_email(email, raw_token)
    except (smtplib.SMTPException, OSError, RuntimeError, ValueError):
        reset.used_at = now()
        db.commit()
        logger.exception("Reset email delivery failed")
        # Keep the response indistinguishable from an unknown email address.
        return response

    return response


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordInput,
    db: Session = Depends(get_db)
):
    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == digest(data.token)
    ).first()

    if not reset or reset.used_at is not None:
        raise HTTPException(
            400,
            "Недействительная или использованная ссылка"
        )

    expires = reset.expires_at

    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if expires <= now():
        raise HTTPException(
            400,
            "Срок действия ссылки истёк"
        )

    client = db.get(ChatClient, reset.client_id)

    if not client:
        raise HTTPException(400, "Аккаунт не найден")

    client.password_hash = passwords.hash(data.new_password)
    reset.used_at = now()

    db.query(ChatLoginToken).filter(
        ChatLoginToken.client_id == client.id
    ).delete(synchronize_session=False)

    db.query(PasswordResetToken).filter(
        PasswordResetToken.client_id == client.id,
        PasswordResetToken.id != reset.id,
        PasswordResetToken.used_at.is_(None)
    ).update(
        {"used_at": now()},
        synchronize_session=False
    )

    db.commit()

    return {
        "ok": True,
        "message": "Пароль изменён. Войдите снова"
    }
