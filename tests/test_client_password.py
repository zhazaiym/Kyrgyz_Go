from tests.test_main_regressions import PASSWORD, headers, register


def test_password_change_signs_out_every_other_device(client):
    account, email = register(client)
    other = client.post('/account/login', json={'email': email, 'password': PASSWORD}).json()
    new_password = PASSWORD + 'new'
    wrong = client.post(
        '/account/password',
        json={'current_password': 'wrong-password', 'new_password': new_password},
        headers=headers(account),
    )
    assert wrong.status_code == 401
    changed = client.post(
        '/account/password',
        json={'current_password': PASSWORD, 'new_password': new_password},
        headers=headers(account),
    )
    assert changed.status_code == 200, changed.text
    assert client.get('/account/me', headers=headers(account)).status_code == 401
    assert client.get('/account/me', headers=headers(other)).status_code == 401
    assert client.get('/account/me', headers=headers(changed.json())).status_code == 200
    old = client.post('/account/login', json={'email': email, 'password': PASSWORD})
    assert old.status_code == 401
    new = client.post('/account/login', json={'email': email, 'password': new_password})
    assert new.status_code == 200


def test_logout_everywhere_revokes_all_tokens(client):
    account, email = register(client)
    other = client.post('/account/login', json={'email': email, 'password': PASSWORD}).json()
    assert client.post('/account/logout-all', headers=headers(account)).status_code == 204
    assert client.get('/account/me', headers=headers(account)).status_code == 401
    assert client.get('/account/me', headers=headers(other)).status_code == 401
