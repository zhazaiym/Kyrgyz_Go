from decimal import Decimal
from itertools import count
from uuid import uuid4

import pytest

from mysite.api.trip_options import distance_km
from mysite.database.db import SessionLocal
from mysite.database.models import Country, District, Hotel, Region, Tour, Transport

# Each fixture gets its own remote spot (~375 km apart) so catalogue rows made
# by other tests are never "near" the tour under test.
spots = count()


def shifted(base, km_north):
    """Coordinates ``km_north`` kilometres north of ``base``."""
    return base[0] + Decimal(str(round(km_north / 111.195, 7))), base[1]


@pytest.fixture
def trip(client):
    suffix = uuid4().hex[:8]
    BASE = (Decimal('47.5000000'), Decimal(-170 + 5 * (next(spots) % 68)))
    with SessionLocal() as db:
        country = Country(name='Trip country ' + suffix)
        other_country = Country(name='Other country ' + suffix)
        region = Region(name='Trip region ' + suffix, country=country)
        other_region = Region(name='Other region ' + suffix, country=other_country)
        district = District(name='Trip district ' + suffix, region=region)
        other_district = District(name='Other district ' + suffix, region=other_region)
        db.add_all([country, other_country, region, other_region, district, other_district])
        db.flush()

        tour = Tour(
            title='Trip tour ' + suffix,
            price=100,
            latitude=BASE[0],
            longitude=BASE[1],
            min_people=2,
            max_people=8,
            country_id=country.id,
        )
        tour_without_point = Tour(
            title='Country tour ' + suffix, price=100, min_people=1, country_id=country.id
        )

        def hotel(name, km, *, place=(region, district), **extra):
            point = shifted(BASE, km) if km is not None else (None, None)
            row = Hotel(
                name=f'{name} {suffix}',
                region=place[0],
                district=place[1],
                price=extra.pop('price', 50),
                latitude=point[0],
                longitude=point[1],
                **extra,
            )
            db.add(row)
            return row

        near = hotel('Near hotel', 5)
        middle = hotel('Middle hotel', 40)
        far = hotel('Far hotel', 400)
        hidden = hotel('Hidden hotel', 1, is_active=False)
        demo = Hotel(
            name='ТЕСТ: demo hotel ' + suffix,
            region=region,
            district=district,
            price=1,
            latitude=BASE[0],
            longitude=BASE[1],
        )
        db.add(demo)
        unplaced_home = hotel('Unplaced home hotel', None, price=30)
        unplaced_abroad = hotel(
            'Unplaced abroad hotel', None, place=(other_region, other_district), price=10
        )

        def vehicle(name, seats, km, **extra):
            point = shifted(BASE, km) if km is not None else (None, None)
            row = Transport(
                name=f'{name} {suffix}',
                seats=seats,
                price=extra.pop('price', 20),
                latitude=point[0],
                longitude=point[1],
                **extra,
            )
            db.add(row)
            return row

        car = vehicle('Near car', 4, 3)
        van = vehicle('Middle van', 12, 30)
        bike = vehicle('Near scooter', 1, 1)
        far_bus = vehicle('Far bus', 40, 600)
        anywhere_bus = vehicle('Unplaced bus', 30, None)
        db.add_all([tour, tour_without_point])
        db.commit()
        ids = {
            name: row.id
            for name, row in {
                'tour': tour,
                'tour_without_point': tour_without_point,
                'near': near,
                'middle': middle,
                'far': far,
                'hidden': hidden,
                'demo': demo,
                'unplaced_home': unplaced_home,
                'unplaced_abroad': unplaced_abroad,
                'car': car,
                'van': van,
                'bike': bike,
                'far_bus': far_bus,
                'anywhere_bus': anywhere_bus,
            }.items()
        }
    return ids


def item_ids(response):
    assert response.status_code == 200, response.text
    return [item['id'] for item in response.json()['items']]


def test_distance_is_great_circle_kilometres():
    assert distance_km((42.87, 74.59), (42.87, 74.59)) == 0
    # Bishkek -> Karakol is roughly 300 km in a straight line.
    assert 290 < distance_km((42.8746, 74.5698), (42.4907, 78.3936)) < 330


def test_step_two_offers_only_near_hotels_nearest_first(client, trip):
    response = client.get(f'/tours/{trip["tour"]}/hotel-options/', params={'limit': 50})
    ids = item_ids(response)
    assert ids[:2] == [trip['near'], trip['middle']]
    for excluded in ('far', 'hidden', 'demo', 'unplaced_home', 'unplaced_abroad'):
        assert trip[excluded] not in ids
    body = response.json()
    assert body['step'] == 'hotel'
    assert body['basis'] == 'distance'
    assert body['radius_km'] == 100
    assert 4.5 < body['items'][0]['distance_km'] < 5.5
    assert body['items'][0]['name'].startswith('Near hotel')


def test_radius_is_configurable(client, trip, monkeypatch):
    monkeypatch.setenv('TRIP_OPTION_RADIUS_KM', '10')
    ids = item_ids(client.get(f'/tours/{trip["tour"]}/hotel-options/'))
    assert trip['near'] in ids and trip['middle'] not in ids


def test_tour_without_coordinates_falls_back_to_its_country(client, trip):
    response = client.get(
        f'/tours/{trip["tour_without_point"]}/hotel-options/', params={'limit': 50}
    )
    ids = item_ids(response)
    assert response.json()['basis'] == 'country'
    assert trip['unplaced_home'] in ids and trip['near'] in ids
    assert trip['unplaced_abroad'] not in ids
    assert trip['hidden'] not in ids and trip['demo'] not in ids
    assert all(item['distance_km'] is None for item in response.json()['items'])


def test_step_three_offers_vehicles_that_fit_the_group_nearest_first(client, trip):
    response = client.get(
        f'/tours/{trip["tour"]}/transport-options/', params={'travelers': 6, 'limit': 50}
    )
    ids = item_ids(response)
    assert ids[0] == trip['van']
    assert trip['anywhere_bus'] in ids
    assert ids.index(trip['van']) < ids.index(trip['anywhere_bus'])
    for excluded in ('car', 'bike', 'far_bus'):
        assert trip[excluded] not in ids
    assert response.json()['travelers'] == 6


def test_transport_defaults_to_tour_minimum_group(client, trip):
    ids = item_ids(client.get(f'/tours/{trip["tour"]}/transport-options/', params={'limit': 50}))
    assert ids[:2] == [trip['car'], trip['van']]
    assert trip['bike'] not in ids  # one seat cannot carry the minimum of two


def test_group_larger_than_tour_allows_is_rejected(client, trip):
    response = client.get(f'/tours/{trip["tour"]}/transport-options/', params={'travelers': 9})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_travelers_count'


def test_unknown_tour_has_no_options(client):
    assert client.get('/tours/2147483647/hotel-options/').status_code == 404
    assert client.get('/tours/2147483647/transport-options/').status_code == 404


def test_selection_walks_through_the_steps(client, customer_headers, trip):
    created = client.post(
        '/travel-selections/', json={'tour_id': trip['tour']}, headers=customer_headers
    )
    assert created.status_code == 201, created.text
    selection = created.json()['id']
    next_step = f'/travel-selections/{selection}/next-step/'

    step = client.get(next_step, headers=customer_headers)
    assert step.json()['step'] == 'hotel'
    assert step.json()['items'][0]['id'] == trip['near']

    chosen = client.patch(
        f'/travel-selections/{selection}/',
        json={'hotel_id': trip['near']},
        headers=customer_headers,
    )
    assert chosen.status_code == 200, chosen.text

    step = client.get(next_step, params={'travelers': 3}, headers=customer_headers)
    assert step.json()['step'] == 'transport'
    assert step.json()['items'][0]['id'] == trip['car']

    chosen = client.patch(
        f'/travel-selections/{selection}/',
        json={'transport_id': trip['car']},
        headers=customer_headers,
    )
    assert chosen.status_code == 200, chosen.text
    assert client.get(next_step, headers=customer_headers).json()['step'] == 'confirm'


def test_selection_rejects_hotel_or_transport_that_does_not_fit_the_tour(
    client, customer_headers, trip
):
    for body, code in (
        ({'tour_id': trip['tour'], 'hotel_id': trip['far']}, 'unsuitable_hotel'),
        ({'tour_id': trip['tour'], 'hotel_id': trip['unplaced_home']}, 'unsuitable_hotel'),
        ({'tour_id': trip['tour'], 'transport_id': trip['far_bus']}, 'unsuitable_transport'),
        ({'tour_id': trip['tour'], 'transport_id': trip['bike']}, 'unsuitable_transport'),
    ):
        response = client.post('/travel-selections/', json=body, headers=customer_headers)
        assert response.status_code == 422, (body, response.text)
        assert response.json()['detail']['code'] == code


def test_selection_without_tour_starts_at_tour_step(client, customer_headers, trip):
    created = client.post(
        '/travel-selections/', json={'hotel_id': trip['far']}, headers=customer_headers
    )
    assert created.status_code == 201
    step = client.get(
        f'/travel-selections/{created.json()["id"]}/next-step/', headers=customer_headers
    )
    assert step.json()['step'] == 'tour'


def test_other_clients_cannot_read_selection_steps(client, customer_headers, trip):
    created = client.post(
        '/travel-selections/', json={'tour_id': trip['tour']}, headers=customer_headers
    )
    stranger = client.post(
        '/auth/register',
        json={'username': 'trip_' + uuid4().hex[:12], 'password': 'StrangerPassword123!'},
    ).json()
    response = client.get(
        f'/travel-selections/{created.json()["id"]}/next-step/',
        headers={'Authorization': 'Bearer ' + stranger['access_token']},
    )
    assert response.status_code == 404
