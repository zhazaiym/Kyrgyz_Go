# ruff: noqa: E402 -- load environment before importing application settings.
"""Enroll one administrator in TOTP MFA and print single-use recovery codes."""

import argparse
import getpass

from dotenv import load_dotenv

load_dotenv()

from mysite.admin.enrollment import enroll_totp
from mysite.api.admin import SECRET_KEY, verify_password
from mysite.api.admin_mfa import consume_admin_mfa
from mysite.database.db import SessionLocal
from mysite.database.models import Admin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('username')
    parser.add_argument(
        '--reset-by',
        help='Owner username authorizing re-enrollment when the target already has MFA',
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        admin = db.query(Admin).filter(Admin.username == args.username).with_for_update().first()
        if admin is None or not admin.is_active:
            raise SystemExit('Active administrator not found')
        if admin.totp_secret_encrypted:
            if not args.reset_by:
                raise SystemExit('MFA is already enrolled; use --reset-by with an owner account')
            actor = db.query(Admin).filter_by(username=args.reset_by).with_for_update().first()
            if (
                actor is None
                or not actor.is_active
                or actor.role != 'owner'
                or not verify_password(getpass.getpass('Owner password: '), actor.hashed_password)
                or not consume_admin_mfa(
                    actor, getpass.getpass('Owner authenticator or recovery code: '), SECRET_KEY
                )
            ):
                raise SystemExit('Owner authorization failed; no changes saved')
            admin.totp_secret_encrypted = None
            admin.totp_last_used_step = None
            admin.recovery_code_hashes = []
        codes = enroll_totp(admin, SECRET_KEY)
        db.commit()
        print('Store these single-use recovery codes securely; they will not be shown again:')
        print('\n'.join(codes))


if __name__ == '__main__':
    main()
