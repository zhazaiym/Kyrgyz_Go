import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from mysite.api import chat_service, password_reset, travel_selection
from mysite.database.chat_models import ChatClient, ChatLoginToken, ChatSession
from mysite.database.db import SessionLocal, engine
from mysite.database.models import District, Hotel, Region, Tour, Transport, TravelRequest
from mysite.database.password_reset_models import PasswordResetToken
from mysite.database.selection_models import TravelSelection

PASSWORD = 'RegressionPassword123!'


def register(client, route='/auth', email=None):
    identity = uuid4().hex[:16]
    email = email or f'{identity}@example.com'
    body = {'email': email, 'password': PASSWORD}
    if route == '/auth':
        body['username'] = 'reg_' + identity
    else:
        body.update(name='Regression Guest', phone='+996700123456')
    response = client.post(route + '/register', json=body)
    assert response.status_code == 201, response.text
    return response.json(), email


def headers(account):
    return {'Authorization': 'Bearer ' + account['access_token']}


@pytest.mark.parametrize('route', ['/auth', '/account'])
def test_registration_login_profile_and_recovery_share_one_identity(client, monkeypatch, route):
    account, email = register(client, route)
    duplicate_body = {'email': email.upper(), 'password': PASSWORD}
    other = '/account' if route == '/auth' else '/auth'
    if other == '/auth':
        duplicate_body['username'] = 'duplicate_' + uuid4().hex[:16]
    else:
        duplicate_body.update(name='Other Guest', phone='+996700123456')
    assert client.post(other + '/register', json=duplicate_body).status_code == 409
    for prefix in ('/auth', '/account', '/chat/auth'):
        login = client.post(prefix + '/login', json={'email': email.upper(), 'password': PASSWORD})
        assert login.status_code == 200, login.text
        assert login.json()['client_id'] == account['client_id']
        me = client.get(prefix + '/me', headers=headers(account))
        assert me.json()['email'] == email
    sent = []
    monkeypatch.setattr(password_reset, 'send_reset_email', lambda e, t: sent.append((e, t)))
    assert client.post('/account/forgot-password', json={'email': email}).status_code == 200
    assert sent[0][0] == email
    new_password = PASSWORD + 'new'
    assert (
        client.post(
            '/account/reset-password', json={'token': sent[0][1], 'new_password': new_password}
        ).status_code
        == 200
    )
    assert client.get('/auth/me', headers=headers(account)).status_code == 401
    for prefix in ('/auth', '/account'):
        assert (
            client.post(prefix + '/login', json={'email': email, 'password': PASSWORD}).status_code
            == 401
        )
        login = client.post(prefix + '/login', json={'email': email, 'password': new_password})
        assert login.status_code == 200
        assert login.json()['client_id'] == account['client_id']


def test_concurrent_registration_cannot_split_email_between_routes(client):
    email = uuid4().hex + '@example.com'
    barrier = Barrier(2)

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO chat_clients'):
            barrier.wait(timeout=10)

    bodies = [
        (
            '/auth/register',
            {'username': 'race_' + uuid4().hex[:16], 'email': email, 'password': PASSWORD},
        ),
        (
            '/account/register',
            {
                'name': 'Race Guest',
                'phone': '+996700123456',
                'email': email.upper(),
                'password': PASSWORD,
            },
        ),
    ]
    event.listen(engine, 'before_cursor_execute', synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(
                pool.map(lambda entry: client.post(entry[0], json=entry[1]).status_code, bodies)
            )
    finally:
        event.remove(engine, 'before_cursor_execute', synchronize)
    assert sorted(statuses) == [201, 409]
    with SessionLocal() as db:
        assert db.query(ChatClient).filter(ChatClient.email == email).count() == 1


@pytest.mark.parametrize('different_tokens', [False, True])
def test_concurrent_password_resets_allow_one_winner(client, monkeypatch, different_tokens):
    account, email = register(client)
    sent = []
    monkeypatch.setattr(password_reset, 'send_reset_email', lambda e, t: sent.append(t))
    for _ in range(2 if different_tokens else 1):
        assert client.post('/account/forgot-password', json={'email': email}).status_code == 200
    tokens = sent if different_tokens else [sent[0], sent[0]]
    barrier = Barrier(2)

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if 'FROM chat_clients' in statement and 'FOR UPDATE' in statement:
            barrier.wait(timeout=10)

    def reset(entry):
        index, token = entry
        with SessionLocal() as db:
            try:
                password_reset.reset_password(
                    password_reset.ResetPasswordInput(
                        token=token, new_password=f'WinningPassword{index}!'
                    ),
                    db,
                )
                return index, 200
            except HTTPException as exc:
                return index, exc.status_code

    event.listen(engine, 'before_cursor_execute', synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reset, enumerate(tokens)))
    finally:
        event.remove(engine, 'before_cursor_execute', synchronize)
    assert sorted(code for _, code in results) == [200, 400]
    winner = next(index for index, code in results if code == 200)
    with SessionLocal() as db:
        identity = db.get(ChatClient, account['client_id'])
        assert password_reset.passwords.verify(f'WinningPassword{winner}!', identity.password_hash)
        assert db.query(ChatLoginToken).filter_by(client_id=identity.id).count() == 0
        assert (
            db.query(PasswordResetToken).filter_by(client_id=identity.id, used_at=None).count() == 0
        )


@pytest.fixture
def selection(client):
    account, _ = register(client)
    suffix = uuid4().hex[:12]
    with SessionLocal() as db:
        region = Region(name='Selection region')
        district = District(name='Selection district', region=region)
        tour = Tour(title='Selected tour', price=100, min_people=1)
        hotel = Hotel(name='Selected hotel ' + suffix, region=region, district=district, price=20)
        transport = Transport(name='Selected transport ' + suffix, seats=4, price=30)
        db.add_all([region, district, tour, hotel, transport])
        db.commit()
        services = [
            {'kind': 'tour', 'id': tour.id, 'name': tour.title},
            {'kind': 'hotel', 'id': hotel.id, 'name': hotel.name},
            {'kind': 'transport', 'id': transport.id, 'name': transport.name},
        ]
    response = client.post(
        '/travel-selections/',
        headers=headers(account),
        json={service['kind'] + '_id': service['id'] for service in services},
    )
    assert response.status_code == 201
    return account, response.json()['id'], services


def test_concurrent_start_chat_returns_one_shared_session(selection):
    account, identity, _ = selection
    barrier = Barrier(2)

    def synchronize(connection, cursor, statement, parameters, context, executemany):
        if 'FROM travel_selections' in statement and 'FOR UPDATE' in statement:
            barrier.wait(timeout=10)

    def start(_):
        with SessionLocal() as db:
            # Preloading also checks that locks refresh the ORM identity map.
            db.get(TravelSelection, identity)
            client = db.get(ChatClient, account['client_id'])
            return travel_selection.start_selection_chat(identity, client, db)

    event.listen(engine, 'before_cursor_execute', synchronize)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, range(2)))
    finally:
        event.remove(engine, 'before_cursor_execute', synchronize)
    assert len({result['session_id'] for result in results}) == 1
    assert sorted(result['existing'] for result in results) == [False, True]
    with SessionLocal() as db:
        assert db.query(ChatSession).filter_by(client_id=account['client_id']).count() == 1


def test_stale_selection_cannot_be_edited_after_start(client, selection):
    account, identity, _ = selection
    with SessionLocal() as db:
        stale = db.get(TravelSelection, identity)
        assert stale.session_id is None
        assert (
            client.post(
                f'/travel-selections/{identity}/start-chat/', headers=headers(account)
            ).status_code
            == 200
        )
        with pytest.raises(HTTPException) as conflict:
            travel_selection.update_selection(
                identity,
                travel_selection.SelectionUpdate(tour_id=None),
                db.get(ChatClient, account['client_id']),
                db,
            )
        assert conflict.value.status_code == 409


def test_selected_services_survive_confirmation_and_catalogue_edits(
    client, admin_headers, monkeypatch, selection
):
    account, identity, services = selection
    started = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()
    sid = started['session_id']

    async def reply(message, state, history, on_chunk=None):
        return (
            'Review request',
            {
                **state,
                'client_name': 'Selected Guest',
                'phone': '+996700123456',
                'travel_date': '2099-06-01',
                'people_count': 2,
            },
            True,
        )

    monkeypatch.setattr(chat_service, 'respond', reply)
    preview = asyncio.run(
        chat_service.process_message(sid, account['client_id'], account['access_token'], 'Book')
    )
    assert preview['booking_preview']['data']['selected_services'] == services
    assert 'Selected hotel' in preview['answer'] and 'Selected transport' in preview['answer']
    payload = {'session_id': sid, 'revision': preview['revision'], 'confirmed': True}
    confirmed = client.post('/booking/confirm', headers=headers(account), json=payload)
    assert confirmed.status_code == 200, confirmed.text
    request_id = confirmed.json()['request_id']
    with SessionLocal() as db:
        request = db.get(TravelRequest, request_id)
        assert request.selected_services == services
        assert 'Selected hotel' in request.message and 'Selected transport' in request.message
        assert db.get(TravelSelection, identity).status == 'in_progress'
        db.get(Hotel, services[1]['id']).name = 'Renamed hotel'
        db.commit()
    stored = client.get(f'/travel-requests/{request_id}/', headers=admin_headers)
    assert stored.status_code == 200
    assert stored.json()['selected_services'] == services
    repeated = client.post('/booking/confirm', headers=headers(account), json=payload)
    assert repeated.status_code == 200 and repeated.json()['request_id'] == request_id


@pytest.mark.parametrize('kind', ['hotel', 'transport'])
def test_unavailable_selected_services_prevent_confirmation(client, selection, kind):
    account, identity, services = selection
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        state = db.get(ChatSession, sid)
        state.state = {
            **state.state,
            'client_name': 'Guest',
            'phone': '+996700123456',
            'travel_date': '2099-06-01',
            'people_count': 2,
        }
        state.stage = 'awaiting_confirmation'
        service = next(item for item in services if item['kind'] == kind)
        db.get(Hotel if kind == 'hotel' else Transport, service['id']).is_active = False
        db.commit()
    preview = client.post(
        '/booking/preview', headers=headers(account), json={'session_id': sid}
    ).json()
    assert not preview['can_confirm'] and f'valid_{kind}' in preview['missing_fields']
    response = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': 0, 'confirmed': True},
    )
    assert response.status_code == 422


def test_catalogue_routes_have_unique_operation_ids_and_keep_public_cards(client, selection):
    account, _, services = selection
    paths = client.get('/openapi.json').json()['paths']
    ids = [
        operation['operationId']
        for methods in paths.values()
        for operation in methods.values()
        if isinstance(operation, dict) and 'operationId' in operation
    ]
    assert len(ids) == len(set(ids))
    for path, service in [('/hotels/', services[1]), ('/transports/', services[2])]:
        response = client.get(path, params={'search': service['name'], 'limit': 1})
        assert response.status_code == 200
        assert len(response.json()) == 1 and response.json()[0]['id'] == service['id']
        assert 'description' not in response.json()[0]
        assert client.get(path + str(service['id']) + '/').status_code == 401
        assert (
            client.get(path + str(service['id']) + '/', headers=headers(account)).status_code == 200
        )
