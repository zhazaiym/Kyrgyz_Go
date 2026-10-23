
import re
import secrets

from email_validator import validate_email, EmailNotValidError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.chat_models import ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.api.chat_auth import issue_token, current_client


router = APIRouter(
    prefix="/account",
    tags=["Tourist Account"]
)

passwords = PasswordHash.recommended()


class RegisterInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=25)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: str
    password: str


def normalize_email(value: str):
    try:
        result = validate_email(
            value.strip(),
            check_deliverability=False
        )
        return result.normalized.lower()

    except EmailNotValidError:
        raise HTTPException(
            status_code=422,
            detail="Введите корректный email"
        )


@router.post("/register", status_code=201)
def register(
    data: RegisterInput,
    db: Session = Depends(get_db)
):
    name = data.name.strip()
    email = normalize_email(data.email)

    phone = re.sub(
        r"[\s()\-]",
        "",
        data.phone.strip()
    )

    if not name:
        raise HTTPException(422, "Укажите имя")

    if not re.fullmatch(r"\+?[0-9]{7,15}", phone):
        raise HTTPException(
            422,
            "Введите корректный номер телефона"
        )

    existing = db.query(ClientProfile).filter(
        ClientProfile.email == email
    ).first()

    if existing:
        raise HTTPException(
            409,
            "Этот email уже зарегистрирован"
        )

    username = "u_" + secrets.token_hex(16)

    client = ChatClient(
        username=username,
        password_hash=passwords.hash(data.password)
    )

    db.add(client)

    try:
        db.flush()

        profile = ClientProfile(
            client_id=client.id,
            name=name,
            phone=phone,
            email=email
        )

        db.add(profile)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "Этот email уже зарегистрирован"
        )

    db.refresh(client)

    result = issue_token(db, client)

    result.update({
        "name": name,
        "phone": phone,
        "email": email
    })

    return result


@router.post("/login")
def login(
    data: LoginInput,
    db: Session = Depends(get_db)
):
    email = normalize_email(data.email)

    profile = db.query(ClientProfile).filter(
        ClientProfile.email == email
    ).first()

    client = (
        db.get(ChatClient, profile.client_id)
        if profile else None
    )

    if not client or not passwords.verify(
        data.password,
        client.password_hash
    ):
        raise HTTPException(
            401,
            "Неправильный email или пароль"
        )

    result = issue_token(db, client)

    result.update({
        "name": profile.name,
        "phone": profile.phone,
        "email": profile.email
    })

    return result


@router.get("/me")
def my_profile(
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    profile = db.query(ClientProfile).filter(
        ClientProfile.client_id == client.id
    ).first()

    return {
        "client_id": client.id,
        "client_code": f"KG-{client.id:06d}",
        "username": client.username,
        "name": profile.name if profile else None,
        "phone": profile.phone if profile else None,
        "email": profile.email if profile else None
    }
