import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from mysite.api import chat_service
from mysite.api.client_auth import client_by_token, digest
from mysite.database import models as m
from mysite.database.chat_models import ChatBookingLink, ChatLoginToken, ChatSession
from mysite.database.db import SessionLocal
from tests.test_main_regressions import headers, register
from tests.test_main_regressions import selection as selection


@pytest.mark.parametrize('zone', ['UTC', 'Asia/Bishkek', 'America/New_York'])
@pytest.mark.parametrize('seconds', [-60, 3600])
def test_token_expiration_uses_instant_not_database_timezone(client, zone, seconds):
    account, _ = register(client)
    with SessionLocal() as db:
        access = (
            db.query(ChatLoginToken).filter_by(token_hash=digest(account['access_token'])).one()
        )
        access.expires_at = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        db.commit()
        db.execute(text('SET LOCAL TIME ZONE :zone'), {'zone': zone})
        if seconds < 0:
            with pytest.raises(HTTPException) as expired:
                client_by_token(db, account['access_token'])
            assert expired.value.status_code == 401
        else:
            assert client_by_token(db, account['access_token']).id == account['client_id']


@pytest.mark.parametrize('token', [123, True, [], {}, None, '', 'x' * 257])
def test_websocket_rejects_malformed_authentication_without_crashing(client, token):
    account, _ = register(client)
    sid = client.post('/chat/session', headers=headers(account)).json()['session_id']
    with client.websocket_connect(
        f'/ws/chat/{sid}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        error = socket.receive_json()
        assert error['type'] == 'error' and error['code'] == 'authentication_failed'
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008


@pytest.fixture
def filtered_tours():
    marker = 'TourFilter' + uuid4().hex[:12]
    with SessionLocal() as db:
        country = m.Country(name=marker)
        category = m.TourCategory(name=marker)
        low = m.Tour(
            title=marker + ' low',
            category=category,
            country=country,
            price=25,
            duration_days=2,
            min_people=1,
            max_people=2,
            description='Private description',
        )
        high = m.Tour(
            title=marker + ' high',
            category=category,
            country=country,
            price=200,
            duration_days=7,
            min_people=3,
            max_people=4,
        )
        db.add_all([country, category, low, high])
        db.commit()
        return marker, low.id, high.id, country.id, category.id


@pytest.mark.parametrize(
    'parameters,which',
    [
        ({'price__lte': 50}, 'low'),
        ({'price__gte': 100}, 'high'),
        ({'duration_days__lte': 3}, 'low'),
        ({'guests': 3}, 'high'),
        ({'order_by': 'price', 'limit': 1, 'offset': 1}, 'high'),
        ({'price__lte': 1}, 'none'),
    ],
)
def test_tour_filters_are_applied_before_pagination(client, filtered_tours, parameters, which):
    marker, low, high, country, category = filtered_tours
    response = client.get(
        '/tours/',
        params={'search': marker, 'country_id': country, 'category_id': category, **parameters},
    )
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == {'low': [low], 'high': [high], 'none': []}[
        which
    ]
    assert all('description' not in row for row in response.json())


def test_public_tour_category_cannot_bypass_private_details(
    client, filtered_tours, customer_headers
):
    _, low, _, _, category = filtered_tours
    response = client.get(f'/tours/category/{category}/')
    assert response.status_code == 200
    assert all(not {'description', 'included', 'excluded'} & row.keys() for row in response.json())
    assert client.get(f'/tours/{low}/').status_code == 401
    assert (
        client.get(f'/tours/{low}/', headers=customer_headers).json()['description']
        == 'Private description'
    )


@pytest.mark.parametrize(
    'kind,path,field',
    [
        ('hotel', '/hotels/', 'name'),
        ('transport', '/transports/', 'name'),
        ('trekking', '/trekkings/', 'title'),
        ('helicopter', '/helicopter-tours/', 'title'),
        ('region', '/regions/', 'name'),
        ('district', '/districts/', 'name'),
        ('tour', '/tours/', 'title'),
    ],
)
def test_search_and_sort_use_displayed_language_before_pagination(client, kind, path, field):
    from mysite.translations.content import mark_manual_translations
    from mysite.translations.source import source_field_hash

    marker = 'Localized' + uuid4().hex[:10]
    with SessionLocal() as db:
        region = m.Region(name='Base region')
        district = m.District(name='Base district', region=region)
        db.add_all([region, district])
        db.flush()
        rows = []
        for original, translated in [('Z original', 'Alpha'), ('A original', 'Zulu')]:
            attributes = {field: original + marker}
            if kind not in ('region', 'district'):
                attributes['price'] = 10
            if kind == 'hotel':
                attributes.update(region_id=region.id, district_id=district.id)
            if kind == 'transport':
                attributes['seats'] = 4
            if kind == 'district':
                attributes['region_id'] = region.id
            model = {
                'hotel': m.Hotel,
                'transport': m.Transport,
                'trekking': m.Trekking,
                'helicopter': m.HelicopterTour,
                'region': m.Region,
                'district': m.District,
                'tour': m.Tour,
            }[kind]
            if kind != 'tour':
                original = original + marker
                attributes['translations'] = mark_manual_translations(
                    {'en': {field: marker + ' ' + translated}}, {field: original}
                )
            row = model(**attributes)
            db.add(row)
            db.flush()
            if kind == 'tour':
                db.add(
                    m.TourTranslation(
                        tour_id=row.id,
                        lang='en',
                        title=marker + ' ' + translated,
                        source_hashes={'title': source_field_hash(row.title)},
                    )
                )
            rows.append(row)
        db.commit()
        expected = rows[0].id
    response = client.get(
        path, params={'lang': 'en', 'search': marker, 'order_by': field, 'limit': 1}
    )
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [expected]
    assert response.json()[0][field] == marker + ' Alpha'


@pytest.mark.parametrize('translation', ['', None, 123, {'invalid': 'nested value'}])
def test_localized_search_falls_back_for_unusable_translation(client, translation):
    marker = 'Fallback' + uuid4().hex[:10]
    with SessionLocal() as db:
        row = m.Region(name=marker, translations={'en': {'name': translation}})
        db.add(row)
        db.commit()
        identity = row.id
    response = client.get('/regions/', params={'lang': 'en', 'search': marker})
    assert response.status_code == 200, response.text
    assert [row['id'] for row in response.json()] == [identity]
    assert response.json()[0]['name'] == marker


@pytest.mark.parametrize(
    'path,parameters',
    [
        ('/hotels/', {'order_by': 'translations'}),
        ('/hotels/', {'order_by': 'images'}),
        ('/hotels/', {'order_by': 'amenities'}),
        ('/regions/', {'order_by': 'country'}),
        ('/hotels/', {'offset': 2**63}),
        ('/tours/', {'offset': 2**63}),
        ('/tours/', {'price__gte': 100, 'price__lte': 1}),
        ('/tours/', {'guests': 0}),
    ],
)
def test_invalid_catalogue_parameters_return_422_not_database_errors(client, path, parameters):
    assert client.get(path, params=parameters).status_code == 422


def complete(state):
    return {
        **state,
        'client_name': 'Original Guest',
        'phone': '+996700123456',
        'travel_date': '2099-06-01',
        'people_count': 2,
    }


def submit(client, selection):
    account, identity, _ = selection
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        row = db.get(ChatSession, sid)
        row.state = complete(row.state)
        row.stage = 'awaiting_confirmation'
        db.commit()
    response = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': 0, 'confirmed': True},
    )
    assert response.status_code == 200, response.text
    return sid, response.json()['request_id']


@pytest.mark.parametrize('intent', [False, True])
def test_corrections_cannot_silently_mutate_or_resubmit_sent_request(
    client, monkeypatch, selection, intent
):
    account, _, _ = selection
    sid, request_id = submit(client, selection)

    async def changed(message, state, history, on_chunk=None):
        return ('Your changes are saved', {**state, 'client_name': 'Changed name'}, intent)

    monkeypatch.setattr(chat_service, 'respond', changed)
    result = asyncio.run(
        chat_service.process_message(
            sid, account['client_id'], account['access_token'], 'Change my name'
        )
    )
    assert result['stage'] == 'submitted' and result['revision'] == 0
    assert not result['booking_intent'] and result['booking_preview'] is None
    assert 'менеджеру' in result['answer']
    with SessionLocal() as db:
        assert db.get(ChatSession, sid).state['client_name'] == 'Original Guest'
        assert db.get(m.TravelRequest, request_id).name == 'Original Guest'
        assert db.query(ChatBookingLink).filter_by(session_id=sid).count() == 1
    repeated = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': 0, 'confirmed': True},
    )
    assert repeated.status_code == 200 and repeated.json()['request_id'] == request_id


@pytest.mark.parametrize('status', ['in_progress', 'completed', 'cancelled'])
def test_request_status_changes_are_visible_in_personal_cabinet(
    client, admin_headers, selection, status
):
    account, identity, _ = selection
    _, request_id = submit(client, selection)
    response = client.put(
        f'/travel-requests/{request_id}/', headers=admin_headers, json={'status': status}
    )
    assert response.status_code == 200
    assert (
        client.get(f'/travel-selections/{identity}/', headers=headers(account)).json()['status']
        == status
    )
    mine = client.get('/travel-selections/me/', headers=headers(account)).json()
    assert next(row for row in mine if row['id'] == identity)['status'] == status


def test_manager_selection_status_updates_linked_request(client, admin_headers, selection):
    account, identity, _ = selection
    _, request_id = submit(client, selection)
    response = client.patch(
        f'/manager/travel-selections/{identity}/status/',
        headers=admin_headers,
        json={'status': 'completed'},
    )
    assert response.status_code == 200, response.text
    assert (
        client.get(f'/travel-requests/{request_id}/', headers=admin_headers).json()['status']
        == 'completed'
    )
    assert (
        client.get(f'/travel-selections/{identity}/', headers=headers(account)).json()['status']
        == 'completed'
    )


def test_sqladmin_status_edit_is_visible_without_a_separate_sync_write(client, selection):
    account, identity, _ = selection
    _, request_id = submit(client, selection)
    # SQLAdmin commits the request model directly. The cabinet must read it,
    # rather than rely on an API-only hook that SQLAdmin would bypass.
    with SessionLocal() as db:
        db.get(m.TravelRequest, request_id).status = m.RequestStatusChoices.cancelled
        db.commit()
    assert (
        client.get(f'/travel-selections/{identity}/', headers=headers(account)).json()['status']
        == 'cancelled'
    )


@pytest.mark.parametrize(
    'email', ['not-an-email', 'a' * 256 + '@example.com', 123, ['a@example.com']]
)
def test_booking_boundary_validates_email_even_if_ai_returns_invalid_state(
    client, selection, email
):
    account, identity, _ = selection
    sid = client.post(
        f'/travel-selections/{identity}/start-chat/', headers=headers(account)
    ).json()['session_id']
    with SessionLocal() as db:
        row = db.get(ChatSession, sid)
        row.state = {**complete(row.state), 'email': email}
        row.stage = 'awaiting_confirmation'
        db.commit()
    preview = client.post('/booking/preview', headers=headers(account), json={'session_id': sid})
    assert not preview.json()['can_confirm'] and 'valid_email' in preview.json()['missing_fields']
    confirmed = client.post(
        '/booking/confirm',
        headers=headers(account),
        json={'session_id': sid, 'revision': 0, 'confirmed': True},
    )
    assert confirmed.status_code == 409
    assert confirmed.json()['detail']['code'] == 'booking_needs_update'
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=sid).count() == 0
