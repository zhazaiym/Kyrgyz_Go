import asyncio
import re
import tracemalloc
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from mysite.database.db import SessionLocal
from mysite.database.models import Tour, TravelRequest


def sql_login(client):
    return client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )


def test_single_admin_request_section_includes_site_requests(client, admin_headers):
    with SessionLocal() as db:
        record = TravelRequest(name='Site request ' + uuid4().hex, phone='+996700123456')
        db.add(record)
        db.commit()
        name, identity = record.name, record.id
    sql_login(client)
    page = client.get('/admin/travel-request/list')
    assert page.status_code == 200 and name in page.text
    assert '/admin/chat-request/list' not in page.text
    assert client.get(f'/admin/travel-request/edit/{identity}').status_code == 200
    assert 'source' in page.text


def test_sqladmin_selected_tour_deletion_is_rejected_without_500(
    client, admin_headers, customer_headers
):
    tour = client.post(
        '/tours/', json={'title': 'Selected deletion probe', 'price': '100'}, headers=admin_headers
    ).json()
    selection = client.post(
        '/travel-selections/', json={'tour_id': tour['id']}, headers=customer_headers
    )
    assert selection.status_code in (200, 201), selection.text
    sql_login(client)
    response = client.delete('/admin/tour/delete', params={'pks': tour['id']})
    assert response.status_code == 200 and 'error=' in response.text
    with SessionLocal() as db:
        assert db.get(Tour, tour['id']) is not None


def test_documented_runtime_commands_are_in_docker_image():
    dockerfile = Path('Dockerfile').read_text()
    for name in set(
        re.findall(r'python -m scripts\.([a-z_]+)', Path('DEPLOY.md').read_text(encoding='utf-8'))
    ):
        assert f'scripts/{name}.py' in dockerfile or 'scripts/ ./scripts/' in dockerfile


def test_upload_returns_host_independent_relative_path(client, admin_headers):
    image = BytesIO()
    Image.new('RGB', (32, 32), 'teal').save(image, 'JPEG')
    response = client.post(
        '/admin/media/',
        files={'file': ('photo.jpg', image.getvalue(), 'image/jpeg')},
        headers={**admin_headers, 'Host': 'untrusted.example'},
    )
    assert response.status_code == 201, response.text
    assert response.json()['url'].startswith('/media/')


def test_large_jpeg_processing_does_not_duplicate_compressed_buffer():
    from mysite.api.media import store_image

    image = BytesIO()
    Image.new('RGB', (6000, 4000), 'teal').save(image, 'JPEG')
    image.seek(0)
    tracemalloc.start()
    try:
        store_image(image)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 12 * 1024 * 1024


def test_unauthenticated_upload_does_not_consume_large_body():
    from main import app

    consumed, output = [], []

    async def receive():
        consumed.append(True)
        return {'type': 'http.request', 'body': b'x' * 1024 * 1024, 'more_body': len(consumed) < 10}

    async def send(message):
        output.append(message)

    scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': 'POST',
        'path': '/admin/media/',
        'raw_path': b'/admin/media/',
        'query_string': b'',
        'headers': [(b'content-type', b'multipart/form-data; boundary=x')],
        'scheme': 'http',
        'client': ('127.0.0.1', 123),
        'server': ('testserver', 80),
    }
    asyncio.run(app(scope, receive, send))
    assert output[0]['status'] == 401
    assert len(consumed) <= 2


@pytest.mark.parametrize(
    'value,valid',
    [
        ('+996 (700) 123-456', True),
        ('+49 30 123456', True),
        ('++1234567', False),
        ('abcdefg', False),
        ('123456', False),
    ],
)
def test_phone_validation_agrees_at_both_entry_points(value, valid):
    from pydantic import ValidationError

    from mysite.api.chat_service import build_preview
    from mysite.api.travel_request import TravelRequestCreate
    from mysite.database.chat_models import ChatSession

    for schema, payload in (
        (
            TravelRequestCreate,
            {'selection_id': 1, 'travel_date': '2099-01-01', 'travelers_count': 1},
        ),
    ):
        try:
            schema(**payload, phone=value)
            accepted = True
        except ValidationError:
            accepted = False
        assert accepted == valid
    with SessionLocal() as db:
        preview = build_preview(
            db,
            ChatSession(
                id=str(uuid4()), client_id=1, revision=0, stage='collecting', state={'phone': value}
            ),
        )
    assert ('phone' not in preview['missing_fields']) == valid


def test_api_errors_have_consistent_codes_and_russian_messages(client, customer_headers):
    for route in ('/countries/2147483647/', '/tours/2147483647/'):
        response = client.get(route, headers=customer_headers)
        assert response.status_code == 404
        assert response.json()['detail'] == {'code': 'not_found', 'message': 'Запись не найдена'}


def test_direct_request_rejects_yesterday_in_bishkek_before_utc_midnight(
    client, customer_headers, monkeypatch
):
    from datetime import datetime, timezone

    from mysite.api import travel_request
    from mysite.dates import bishkek_today

    instant = datetime(2026, 11, 7, 23, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(travel_request, 'bishkek_today', lambda: bishkek_today(instant))
    response = client.post(
        '/travel-requests/',
        headers=customer_headers,
        json={
            'selection_id': 2147483647,
            'travel_date': '2026-11-07',
            'travelers_count': 1,
            'phone': '+996700123456',
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize('count', [40, 3_000_000_000])
def test_direct_request_respects_tour_and_storage_people_limits(
    client, admin_headers, customer_headers, count
):
    tour = client.post(
        '/tours/',
        headers=admin_headers,
        json={'title': 'Capacity probe', 'price': '100', 'min_people': 1, 'max_people': 6},
    ).json()
    selection = client.post(
        '/travel-selections/', headers=customer_headers, json={'tour_id': tour['id']}
    ).json()
    response = client.post(
        '/travel-requests/',
        headers=customer_headers,
        json={
            'selection_id': selection['id'],
            'travel_date': '2099-01-01',
            'travelers_count': count,
            'phone': '+996700123456',
        },
    )
    assert response.status_code == 422
