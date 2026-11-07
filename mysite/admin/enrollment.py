"""Interactive enrollment shared by administrator creation and MFA reset."""

import getpass
from urllib.parse import quote

from mysite.api.admin_mfa import (encrypt_totp_secret, generate_recovery_codes,
                                  generate_totp_secret, hash_recovery_code, matching_totp_step)


def enroll_totp(admin, secret_key):
    secret = generate_totp_secret()
    print(f'TOTP secret (one-time display): {secret}')
    print(
        f'otpauth://totp/Kerben%20Travel:{quote(admin.username, safe="")}?secret={secret}'
        '&issuer=Kerben%20Travel&algorithm=SHA1&digits=6&period=30'
    )
    step = matching_totp_step(secret, getpass.getpass('Enter current authenticator code: '))
    if step is None:
        raise SystemExit('Code did not verify; no changes saved')
    codes = generate_recovery_codes()
    admin.totp_secret_encrypted = encrypt_totp_secret(secret, secret_key)
    admin.totp_last_used_step = step
    admin.recovery_code_hashes = [hash_recovery_code(code) for code in codes]
    return codes
