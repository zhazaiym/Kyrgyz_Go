from mysite.api.admin_mfa import (consume_admin_mfa, decrypt_totp_secret, encrypt_totp_secret,
                                  generate_recovery_codes, generate_totp_secret, hash_recovery_code,
                                  totp_code, verify_totp)


def test_totp_matches_rfc_6238_six_digit_vector():
    secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    assert totp_code(secret, 59) == '287082'
    assert verify_totp(secret, '287082', 59)
    assert not verify_totp(secret, '287083', 59)


def test_totp_secret_is_encrypted_and_bound_to_app_secret():
    secret = generate_totp_secret()
    ciphertext = encrypt_totp_secret(secret, 'app-key-one')
    assert secret not in ciphertext
    assert decrypt_totp_secret(ciphertext, 'app-key-one') == secret


def test_recovery_codes_are_random_and_only_hashes_are_persistable():
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    assert hash_recovery_code(codes[0]) != codes[0]


def test_recovery_code_can_only_be_consumed_once():
    from types import SimpleNamespace

    from mysite.api.admin_mfa import encrypt_totp_secret

    code = 'a1b2c3d4e5'
    admin = SimpleNamespace(
        totp_secret_encrypted=encrypt_totp_secret(generate_totp_secret(), 'app-key'),
        recovery_code_hashes=[hash_recovery_code(code)],
    )
    assert consume_admin_mfa(admin, code, 'app-key')
    assert not consume_admin_mfa(admin, code, 'app-key')
    assert admin.recovery_code_hashes == []


def test_totp_code_cannot_be_replayed(monkeypatch):
    from types import SimpleNamespace

    import mysite.api.admin_mfa as mfa

    secret = generate_totp_secret()
    admin = SimpleNamespace(
        totp_secret_encrypted=encrypt_totp_secret(secret, 'app-key'),
        recovery_code_hashes=[],
        totp_last_used_step=None,
    )
    monkeypatch.setattr(mfa.time, 'time', lambda: 120)
    code = totp_code(secret, 120)
    assert consume_admin_mfa(admin, code, 'app-key')
    assert not consume_admin_mfa(admin, code, 'app-key')


def test_admin_role_matrix_only_grants_scoped_route_groups():
    from mysite.api.admin import admin_role_allows

    assert admin_role_allows('owner', '/admin/admins')
    assert admin_role_allows('manager', '/admin/requests/')
    assert admin_role_allows('manager', '/manager/travel-selections/')
    assert not admin_role_allows('manager', '/admin/media/')
    assert admin_role_allows('catalog_editor', '/tours/12/translate/')
    assert not admin_role_allows('catalog_editor', '/admin/requests/')
    assert not admin_role_allows('catalog_editor', '/admin/admins/')
