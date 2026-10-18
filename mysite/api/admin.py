
from datetime import datetime, timedelta, timezone
import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Admin
from mysite.database.schema import AdminLoginSchema, AdminOutSchema, TokenSchema

load_dotenv()

admin_router = APIRouter(prefix="/admin", tags=["Admin"])

oauth2_schema = HTTPBearer()
password_hash = PasswordHash.recommended()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY .env файлында көрсөтүлүшү керек")


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_schema),
    db: Session = Depends(get_db)
) -> Admin:
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Токен жараксыз же мөөнөтү бүткөн",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_id = payload.get("sub")

        if admin_id is None:
            raise credentials_exception

        admin_id = int(admin_id)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    admin_db = db.get(Admin, admin_id)

    if admin_db is None or not admin_db.is_active:
        raise credentials_exception

    return admin_db


@admin_router.post("/login/", response_model=TokenSchema)
def login_admin(admin: AdminLoginSchema, db: Session = Depends(get_db)):
    admin_db = db.query(Admin).filter(Admin.username == admin.username).first()

    if admin_db is None or not verify_password(admin.password, admin_db.hashed_password):
        raise HTTPException(status_code=401, detail="Логин же пароль туура эмес")

    if not admin_db.is_active:
        raise HTTPException(status_code=403, detail="Админ активдүү эмес")

    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    token = jwt.encode(
        {"sub": str(admin_db.id), "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"access_token": token, "token_type": "bearer"}


@admin_router.get("/me/", response_model=AdminOutSchema)
def get_admin_profile(current_admin: Admin = Depends(get_current_admin)):
    return current_admin
