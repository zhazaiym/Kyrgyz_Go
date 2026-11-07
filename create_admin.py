from getpass import getpass

from pwdlib import PasswordHash

from mysite.admin.enrollment import enroll_totp
from mysite.api.admin import SECRET_KEY
from mysite.database.db import SessionLocal
from mysite.database.models import Admin

password_hash = PasswordHash.recommended()


def create_admin():
    username = input('Админдин логини: ').strip()
    password = getpass('Админдин паролу: ')

    if not username or len(username) > 100 or not 8 <= len(password) <= 128:
        print('Логин: 1–100 символов; пароль: 8–128 символов')
        return

    with SessionLocal() as db:
        existing = db.query(Admin).filter(Admin.username == username).first()
        if existing:
            print('Мындай админ мурунтан бар')
            return

        admin = Admin(
            username=username, hashed_password=password_hash.hash(password), is_active=True
        )
        codes = enroll_totp(admin, SECRET_KEY)
        db.add(admin)
        db.commit()
        print('Store these one-time recovery codes securely:')
        print('\n'.join(codes))
        print('Админ түзүлдү')


if __name__ == '__main__':
    create_admin()
