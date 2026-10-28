import pytest

from mysite.database.db import SessionLocal
from mysite.database.models import TravelRequest


@pytest.mark.parametrize('path', ['/bookings/', '/travel-requests/'])
def test_direct_submission_is_retired_without_creating_request(client, customer_headers, path):
    with SessionLocal() as db:
        before = db.query(TravelRequest).count()
    for headers in ({}, customer_headers):
        response = client.post(
            path,
            headers=headers,
            json={'name': 'Must not be saved', 'phone': '+996700000001', 'tour_id': 1},
        )
        assert response.status_code == 410
        assert response.json()['detail']['code'] == 'booking_requires_chat'
        assert response.json()['detail']['chat_session_url'] == '/chat/session'
    with SessionLocal() as db:
        assert db.query(TravelRequest).count() == before


def test_admin_only_has_chat_requests_view(client, admin_headers):
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    try:
        page = client.get('/admin/')
        assert page.status_code == 200
        assert '/admin/chat-request/list' in page.text
        assert '/admin/travel-request/list' not in page.text
        assert client.get('/admin/travel-request/list').status_code == 404
        assert client.get('/admin/travel-request/create').status_code == 404
    finally:
        client.get('/admin/logout')
