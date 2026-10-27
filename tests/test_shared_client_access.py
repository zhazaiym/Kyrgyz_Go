import pytest

from mysite.database import models
from mysite.database.db import SessionLocal


@pytest.fixture
def catalogue_entries():
    with SessionLocal() as db:
        country = models.Country(name='Access country')
        region = models.Region(name='Access region', country=country)
        district = models.District(name='Access district', region=region)
        entries = [
            (
                '/tours/',
                models.Tour(title='Access tour', price=100, description='Private itinerary'),
            ),
            (
                '/hotels/',
                models.Hotel(
                    name='Access hotel',
                    price=100,
                    region=region,
                    district=district,
                    description='Private accommodation',
                ),
            ),
            (
                '/transports/',
                models.Transport(
                    name='Access transport', price=100, seats=4, description='Private transport'
                ),
            ),
            (
                '/trekkings/',
                models.Trekking(title='Access trek', price=100, description='Private trek'),
            ),
            (
                '/helicopter-tours/',
                models.HelicopterTour(
                    title='Access flight', price=100, description='Private flight'
                ),
            ),
        ]
        db.add_all([country, region, district] + [entry for _, entry in entries])
        db.commit()
        return [(path, entry.id) for path, entry in entries]


def register_customer(client, username, prefix='/auth'):
    response = client.post(
        prefix + '/register', json={'username': username, 'password': 'StrongPassword123!'}
    )
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_guest_sees_cards_but_needs_login_for_details(client, catalogue_entries):
    hidden = {
        'description',
        'included',
        'excluded',
        'instruction',
        'programs',
        'images',
        'phone',
        'amenities',
        'address',
    }
    for path, entry_id in catalogue_entries:
        response = client.get(path, params={'search': 'Access'})
        assert response.status_code == 200
        card = next(item for item in response.json() if item['id'] == entry_id)
        assert not hidden.intersection(card)
        response = client.get(f'{path}{entry_id}/')
        assert response.status_code == 401


@pytest.mark.parametrize('entrypoint', ['/auth', '/chat/auth'])
def test_one_registration_opens_chat_and_details(client, catalogue_entries, entrypoint):
    headers = register_customer(client, 'shared_' + entrypoint.replace('/', '_'), entrypoint)
    assert client.get('/auth/me', headers=headers).status_code == 200
    for path, entry_id in catalogue_entries:
        response = client.get(f'{path}{entry_id}/', headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()['description'].startswith('Private ')
    created = client.post('/chat/session', headers=headers)
    assert created.status_code == 200
    with client.websocket_connect(
        f'/ws/chat/{created.json()["session_id"]}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': headers['Authorization'].split()[1]})
        assert socket.receive_json()['type'] == 'connected'
    assert client.post('/auth/logout', headers=headers).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/chat/session', headers=headers).status_code == 401
    for path, entry_id in catalogue_entries:
        assert client.get(f'{path}{entry_id}/', headers=headers).status_code == 401


@pytest.mark.parametrize(
    'path',
    [
        '/tour-programs/',
        '/trekking-programs/',
        '/tour-images/',
        '/hotel-images/',
        '/transport-images/',
        '/trekking-images/',
        '/helicopter-images/',
    ],
)
def test_guest_cannot_bypass_details_through_nested_resources(client, path):
    assert client.get(path).status_code == 401


def test_shared_auth_is_visible_and_legacy_chat_auth_hidden(client):
    paths = client.get('/openapi.json').json()['paths']
    assert '/auth/register' in paths
    assert '/auth/login' in paths
    assert '/chat/auth/register' not in paths


def test_login_required_response_describes_registration_action(client):
    response = client.post('/chat/session')
    assert response.status_code == 401
    assert response.json()['detail']['register_url'] == '/auth/register'


def test_legacy_and_shared_registration_use_the_same_account(client):
    credentials = {'username': 'single_customer_identity', 'password': 'StrongPassword123!'}
    assert client.post('/auth/register', json=credentials).status_code == 201
    assert client.post('/chat/auth/register', json=credentials).status_code == 409
    login = client.post('/auth/login', json=credentials)
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
    assert client.get('/chat/auth/me', headers=headers).status_code == 200
    assert (
        client.post(
            '/tours/', headers=headers, json={'title': 'Unauthorized creation', 'price': 100}
        ).status_code
        == 401
    )
    assert client.post('/chat/auth/logout', headers=headers).status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401


def test_invalid_token_does_not_open_catalogue_details(client, catalogue_entries):
    headers = {'Authorization': 'Bearer invalid-token'}
    for path, entry_id in catalogue_entries:
        assert client.get(f'{path}{entry_id}/', headers=headers).status_code == 401
        assert client.get(path, headers=headers).status_code == 200
