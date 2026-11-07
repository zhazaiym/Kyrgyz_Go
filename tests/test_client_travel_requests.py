from datetime import date, timedelta
from uuid import uuid4

from mysite.database.db import SessionLocal
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest
from mysite.database.selection_models import TravelSelection


def register_client(client):
    username = 'request_' + uuid4().hex[:20]
    response = client.post(
        '/auth/register', json={'username': username, 'password': 'StrongRequestPassword123!'}
    )
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def create_tour():
    with SessionLocal() as db:
        tour = Tour(title=f'Request tour {uuid4().hex}', price=125, duration_days=4)
        db.add(tour)
        db.commit()
        tour_id = tour.id
    return tour_id


def make_selection(client, headers):
    tour_id = create_tour()
    response = client.post('/travel-selections/', headers=headers, json={'tour_id': tour_id})
    assert response.status_code == 201, response.text
    return response.json()['id'], tour_id


def request_payload(selection_id):
    return {
        'selection_id': selection_id,
        'travel_date': (date.today() + timedelta(days=15)).isoformat(),
        'travelers_count': 3,
        'phone': '+996 (700) 123-456',
        'message': 'Please contact me in the afternoon',
    }


def test_client_can_submit_once_and_cancel_request(client, customer_headers, monkeypatch):
    selection_id, tour_id = make_selection(client, customer_headers)
    published = []

    def publish_after_commit(request_id):
        with SessionLocal() as db:
            assert db.get(TravelRequest, request_id) is not None
        published.append(request_id)

    monkeypatch.setattr('mysite.api.travel_request.publish_new_request', publish_after_commit)
    created = client.post(
        '/travel-requests/', headers=customer_headers, json=request_payload(selection_id)
    )
    assert created.status_code == 201, created.text
    request_id = created.json()['id']
    assert created.json()['phone'] == '+996700123456'
    assert created.json()['travelers_count'] == 3
    assert created.json()['selected_services'][0]['kind'] == 'tour'
    assert created.json()['selected_services'][0]['id'] == tour_id
    assert created.json()['selected_services'][0]['name'].startswith('Request tour ')
    assert published == [request_id]

    with SessionLocal() as db:
        stored = db.get(TravelRequest, request_id)
        assert stored is not None
        assert (
            stored.client_id == client.get('/auth/me', headers=customer_headers).json()['client_id']
        )
        assert stored.selection_id == selection_id
        selection = db.get(TravelSelection, selection_id)
        assert selection.status == 'in_progress'

    repeated = client.post(
        '/travel-requests/', headers=customer_headers, json=request_payload(selection_id)
    )
    assert repeated.status_code == 409

    cancelled = client.delete(f'/travel-requests/me/{request_id}/', headers=customer_headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['status'] == 'cancelled'
    assert (
        client.delete(f'/travel-requests/me/{request_id}/', headers=customer_headers).json()[
            'status'
        ]
        == 'cancelled'
    )
    with SessionLocal() as db:
        assert db.get(TravelRequest, request_id) is not None


def test_request_creation_requires_owned_active_selection(client, customer_headers):
    selection_id, _ = make_selection(client, customer_headers)
    other_headers = register_client(client)
    foreign = client.post(
        '/travel-requests/', headers=other_headers, json=request_payload(selection_id)
    )
    assert foreign.status_code == 404

    with SessionLocal() as db:
        selection = db.get(TravelSelection, selection_id)
        tour = db.get(Tour, selection.tour_id)
        tour.is_active = False
        db.commit()
    inactive = client.post(
        '/travel-requests/', headers=customer_headers, json=request_payload(selection_id)
    )
    assert inactive.status_code == 409


def test_clients_only_list_and_cancel_their_own_requests(client):
    customer_headers = register_client(client)
    first_selection, _ = make_selection(client, customer_headers)
    first = client.post(
        '/travel-requests/', headers=customer_headers, json=request_payload(first_selection)
    )
    assert first.status_code == 201, first.text

    other_headers = register_client(client)
    second_selection, _ = make_selection(client, other_headers)
    second = client.post(
        '/travel-requests/', headers=other_headers, json=request_payload(second_selection)
    )
    assert second.status_code == 201, second.text

    listed = client.get('/travel-requests/me/', headers=customer_headers)
    assert listed.status_code == 200
    assert [row['id'] for row in listed.json()] == [first.json()['id']]
    assert (
        client.delete(
            f'/travel-requests/me/{second.json()["id"]}/', headers=customer_headers
        ).status_code
        == 404
    )

    with SessionLocal() as db:
        completed = db.get(TravelRequest, first.json()['id'])
        completed.status = RequestStatusChoices.completed
        db.commit()
    assert (
        client.delete(
            f'/travel-requests/me/{first.json()["id"]}/', headers=customer_headers
        ).status_code
        == 409
    )


def test_travel_request_requires_auth_and_valid_payload(client):
    assert client.post('/travel-requests/', json=request_payload(1)).status_code == 401
    headers = register_client(client)
    response = client.post('/travel-requests/', headers=headers, json={'selection_id': 1})
    assert response.status_code == 422
