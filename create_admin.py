from getpass import getpass

from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from mysite.database.db import SessionLocal
from mysite.database.models import Admin

password_hash = PasswordHash.recommended()


def create_admin():
    username = input("Админдин логини: ").strip()
    password = getpass("Админдин паролу: ")

    if not username or not password:
        print("Логин жана пароль бош болбошу керек")
        return

    with SessionLocal() as db:
        existing = db.query(Admin).filter(Admin.username == username).first()
        if existing:
            print("Мындай админ мурунтан бар")
            return

        admin = Admin(username=username, hashed_password=password_hash.hash(password), is_active=True)
        db.add(admin)
        db.commit()
        print("Админ түзүлдү")


if __name__ == "__main__":
    create_admin()