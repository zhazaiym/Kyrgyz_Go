from mysite.database.db import SessionLocal
from mysite.database.models import TravelRequest


def test_direct_booking_submission_is_retired_without_creating_request(client, customer_headers):
    with SessionLocal() as db:
        before = db.query(TravelRequest).count()
    for headers in ({}, customer_headers):
        response = client.post(
            '/bookings/',
            headers=headers,
            json={'name': 'Must not be saved', 'phone': '+996700000001', 'tour_id': 1},
        )
        assert response.status_code == 410
        assert response.json()['detail']['code'] == 'booking_requires_chat'
        assert response.json()['detail']['chat_session_url'] == '/chat/session'
    with SessionLocal() as db:
        assert db.query(TravelRequest).count() == before


def test_travel_request_creation_requires_selection_payload(client, customer_headers):
    assert (
        client.post(
            '/travel-requests/',
            json={
                'selection_id': 1,
                'travel_date': '2099-01-01',
                'travelers_count': 1,
                'phone': '+996700000001',
            },
        ).status_code
        == 401
    )
    response = client.post(
        '/travel-requests/',
        headers=customer_headers,
        json={'name': 'Must not be accepted', 'phone': '+996700000001', 'tour_id': 1},
    )
    assert response.status_code == 422


def test_admin_has_one_unified_request_view(client, admin_headers):
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    try:
        page = client.get('/admin/')
        assert page.status_code == 200
        assert '/admin/chat-request/list' not in page.text
        assert '/admin/travel-request/list' in page.text
        assert client.get('/admin/travel-request/list').status_code == 200
        assert client.get('/admin/chat-request/list').status_code == 404
        assert client.get('/admin/travel-request/create').status_code == 403
    finally:
        client.get('/admin/logout')
