from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from mysite.database.db import SessionLocal
from mysite.database.models import Tour
from mysite.database.tour_review_models import TourReview


def create_tour():
    with SessionLocal() as db:
        tour = Tour(title=f'Review test {uuid4().hex}', price=100)
        db.add(tour)
        db.commit()
        return tour.id, tour.title


def register_review_client(client):
    username = 'review_' + uuid4().hex[:20]
    response = client.post(
        '/auth/register', json={'username': username, 'password': 'StrongReviewPassword123!'}
    )
    assert response.status_code == 201, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_reviews_are_public_unique_and_owner_deletable(client, customer_headers):
    tour_id, _ = create_tour()
    url = f'/tours/{tour_id}/reviews/'
    assert client.get(url).status_code == 200
    assert client.post(url, json={'rating': 5, 'text': 'No login'}).status_code == 401

    created = client.post(
        url, headers=customer_headers, json={'rating': 5, 'text': 'Wonderful trip'}
    )
    assert created.status_code == 201, created.text
    review_id = created.json()['id']
    assert set(created.json()) == {'id', 'display_name', 'rating', 'text', 'created_at'}
    assert created.json()['rating'] == 5
    assert created.json()['text'] == 'Wonderful trip'
    assert created.json()['display_name'] == 'catalogue_customer'
    assert 'email' not in created.json()

    assert client.get(url).json()[0]['id'] == review_id
    assert (
        client.post(url, headers=customer_headers, json={'rating': 4, 'text': 'Second'}).status_code
        == 409
    )

    other_headers = register_review_client(client)
    other_review = client.post(url, headers=other_headers, json={'rating': 3, 'text': 'Good'})
    assert other_review.status_code == 201, other_review.text
    assert (
        client.delete(f'{url}{other_review.json()["id"]}/', headers=customer_headers).status_code
        == 404
    )
    assert client.delete(f'{url}{review_id}/', headers=customer_headers).status_code == 204
    assert client.delete(f'{url}{review_id}/', headers=customer_headers).status_code == 404


@pytest.mark.parametrize(
    'payload',
    [
        {'rating': 0, 'text': 'Too low'},
        {'rating': 6, 'text': 'Too high'},
        {'rating': 5, 'text': '   '},
        {'rating': 5, 'text': 'x' * 2001},
    ],
)
def test_reviews_reject_invalid_rating_or_text(client, customer_headers, payload):
    tour_id, _ = create_tour()
    response = client.post(f'/tours/{tour_id}/reviews/', headers=customer_headers, json=payload)
    assert response.status_code == 422


def test_review_list_requires_an_existing_active_tour(client):
    assert client.get('/tours/2147483647/reviews/').status_code == 404


def test_tour_cards_include_review_aggregates(client, customer_headers):
    tour_id, title = create_tour()
    url = f'/tours/{tour_id}/reviews/'
    empty = next(
        row
        for row in client.get('/tours/', params={'search': title}).json()
        if row['id'] == tour_id
    )
    assert empty['average_rating'] is None
    assert empty['review_count'] == 0

    first = client.post(url, headers=customer_headers, json={'rating': 5, 'text': 'Excellent'})
    assert first.status_code == 201
    second_headers = register_review_client(client)
    second = client.post(url, headers=second_headers, json={'rating': 4, 'text': 'Very good'})
    assert second.status_code == 201

    rated = next(
        row
        for row in client.get('/tours/', params={'search': title}).json()
        if row['id'] == tour_id
    )
    assert rated['average_rating'] == 4.5
    assert rated['review_count'] == 2


def test_database_rejects_duplicate_tour_review(client, customer_headers):
    tour_id, _ = create_tour()
    client_id = client.get('/auth/me', headers=customer_headers).json()['client_id']
    with SessionLocal() as db:
        db.add_all(
            [
                TourReview(
                    tour_id=tour_id,
                    client_id=client_id,
                    display_name='Client',
                    rating=5,
                    text='One',
                ),
                TourReview(
                    tour_id=tour_id,
                    client_id=client_id,
                    display_name='Client',
                    rating=4,
                    text='Two',
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            db.commit()
