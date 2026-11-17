from datetime import date, timedelta

import pytest

PUBLIC_LIST_ROUTES = [
    '/',
    '/openapi.json',
    '/tour-categories/',
    '/tours/',
    '/countries/',
    '/regions/',
    '/districts/',
    '/hotels/',
    '/transports/',
    '/helicopter-tours/',
    '/trekkings/',
    '/faqs/',
    '/contacts/',
    '/abouts/',
    '/about-sections/',
]


@pytest.mark.parametrize('path', PUBLIC_LIST_ROUTES)
def test_public_read_routes_respond(client, path):
    response = client.get(path)
    assert response.status_code == 200, f'{path}: {response.text}'


@pytest.mark.parametrize(
    'path',
    [
        '/hotel-images/',
        '/transport-images/',
        '/helicopter-images/',
        '/trekking-images/',
        '/tour-images/',
        '/tour-programs/',
        '/trekking-programs/',
    ],
)
def test_catalogue_detail_resources_are_public(client, customer_headers, path):
    assert client.get(path).status_code == 200
    assert client.get(path, headers=customer_headers).status_code == 200


def test_catalogue_is_read_only_through_the_api(client):
    paths = client.get('/openapi.json').json()['paths']
    writes = {
        path for path, operations in paths.items() for method in operations if method != 'get'
    }
    client_areas = (
        '/account/',
        '/auth/',
        '/chat/',
        '/booking/',
        '/travel-requests/',
        '/travel-selections/',
        '/api/ask-ai/',
        '/tours/{tour_id}/reviews/',
    )
    assert all(path.startswith(client_areas) for path in writes), sorted(writes)


def test_private_customer_routes_reject_anonymous_requests(client):
    request = client.post(
        '/travel-requests/',
        json={
            'selection_id': 1,
            'travel_date': (date.today() + timedelta(days=1)).isoformat(),
            'travelers_count': 1,
            'phone': '+996700123456',
        },
    )
    assert request.status_code == 401
    assert client.get('/travel-requests/').status_code == 405
    for method in ('get', 'put', 'delete'):
        assert client.request(method, '/travel-requests/1/').status_code == 404


def test_openapi_advertises_client_requests_and_chat_booking(client):
    paths = client.get('/openapi.json').json()['paths']
    assert '/bookings/' not in paths
    assert 'post' in paths['/travel-requests/']
    assert paths['/travel-requests/']['post']['security'] == [{'ClientBearer': []}]
    assert '/booking/confirm/' in paths


def test_legacy_booking_submission_requires_chat(client, seed):
    from mysite.database.models import Tour, TourCategory

    category_id = seed(TourCategory, name='Booking category')
    tour = {'id': seed(Tour, category_id=category_id, title='Bookable tour', price=50)}

    response = client.post(
        '/bookings/',
        json={
            'tour_id': tour['id'],
            'name': 'Booking User',
            'phone': '+996700000099',
            'travelers_count': 2,
        },
    )

    assert response.status_code == 410, response.text
    assert response.json()['detail']['code'] == 'booking_requires_chat'
