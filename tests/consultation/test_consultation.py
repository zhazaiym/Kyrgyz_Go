import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault('GEMINI_API_KEY', 'test-key-not-used')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mysite.api.booking_text import preview_text
from mysite.database.db import Base, get_db
from mysite.database.models import Tour, Hotel, Transport, Country, Region, District, TravelRequest
from mysite.database.chat_models import ChatClient, ChatSession, ChatMessage, ChatBookingLink
from mysite.database.selection_models import TravelSelection


@pytest.fixture
def database():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        yield db
    engine.dispose()


@pytest.mark.parametrize('language', ['ru', 'en', 'ky', 'de', 'zh'])
def test_contact_only_preview(language):
    data = dict(language=language, client_name='Anna', phone='+996700123456',
                email='anna@example.com', travel_date='2099-06-01', people_count=4,
                duration_days=7, budget='1500 USD', notes='Quiet room')
    result = preview_text(data, 'Mountain tour').strip()
    for value in ('Anna', '+996700123456', 'anna@example.com'):
        assert value in result
    for value in ('Mountain tour', '2099-06-01', '1500 USD', 'Quiet room'):
        assert value not in result
    assert result.count('\n') == 3


def test_preview_omits_unsupplied_email_and_extra_instructions():
    result = preview_text(dict(client_name='Анна', phone='+996700123456'), None)
    assert result.strip() == 'Проверьте заявку:\nИмя: Анна\nТелефон: +996700123456'


def seed_selection(db):
    country = Country(name='Kyrgyzstan')
    region = Region(name='Issyk Kul', country=country)
    district = District(name='Lake district', region=region)
    client = ChatClient(username='consultation', password_hash='not-used')
    tour = Tour(title='Lake tour', price=100, description='Visit the lake', duration_days=3)
    hotel = Hotel(name='Lake hotel', price=50, region=region, district=district,
                  description='Near the lake', stars=4, amenities=['Wi-Fi'])
    transport = Transport(name='Minivan', price=80, seats=6, has_driver=True)
    db.add_all([client, tour, hotel, transport])
    db.flush()
    selection = TravelSelection(client_id=client.id, tour_id=tour.id,
                                hotel_id=hotel.id, transport_id=transport.id)
    db.add(selection)
    db.commit()
    return client, selection


def test_exact_selected_details_include_hotel_and_transport_facts(database):
    from mysite.chain.tools import selected_service_details
    _, selection = seed_selection(database)
    result = selected_service_details(database, dict(tour_id=selection.tour_id,
        hotel_id=selection.hotel_id, transport_id=selection.transport_id))
    assert result['tour']['title'] == 'Lake tour'
    assert result['hotel']['stars'] == 4
    assert result['hotel']['amenities'] == ['Wi-Fi']
    assert result['transport']['seats'] == 6
    database.get(Hotel, selection.hotel_id).is_active = False
    database.commit()
    result = selected_service_details(database, {'hotel_id': selection.hotel_id})
    assert 'error' in result['hotel']


def test_start_selection_chat_generates_and_persists_consultation(database, monkeypatch):
    from mysite.api import travel_selection as route
    client, selection = seed_selection(database)
    calls = []

    async def welcome(state, details):
        calls.append((state, details))
        return 'Отель расположен у озера. Какой отдых вам интересен и какой бюджет?'

    monkeypatch.setattr(route, 'selection_welcome', welcome)
    app = FastAPI()
    app.include_router(route.selection_router)
    app.dependency_overrides[get_db] = lambda: database
    app.dependency_overrides[route.current_client] = lambda: client
    with TestClient(app) as api:
        first = api.post(f'/travel-selections/{selection.id}/start-chat/').json()
        again = api.post(f'/travel-selections/{selection.id}/start-chat/').json()
    assert len(calls) == 1
    assert calls[0][1]['hotel']['name'] == 'Lake hotel'
    assert 'бюджет' in first['welcome']
    assert again['existing']
    messages = database.query(ChatMessage).filter_by(session_id=first['session_id']).all()
    assert messages[-1].content == first['welcome']
    assert database.get(ChatSession, first['session_id']).stage == 'consultation'


def test_selection_welcome_uses_one_model_call_with_selected_facts(monkeypatch):
    from mysite.chain import agent
    calls = []

    async def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content='Lake hotel: near the lake. What is your budget?')

    monkeypatch.setattr(agent, 'llm', SimpleNamespace(ainvoke=invoke))
    result = asyncio.run(agent.selection_welcome({'hotel_id': 42},
        {'hotel': {'name': 'Lake hotel', 'description': 'Near the lake'}}))
    assert 'Lake hotel' in result
    assert len(calls) == 1
    assert 'Near the lake' in calls[0][-1].content
    # Initial explanation does not need the entire extraction/booking manual.
    assert len(calls[0][0].content) < 5000


def test_confirmation_keeps_full_request_for_manager(database):
    from mysite.api.chat_service import build_preview, confirm_booking
    client, selection = seed_selection(database)
    state = dict(tour_id=selection.tour_id, hotel_id=selection.hotel_id,
        transport_id=selection.transport_id, client_name='Anna', phone='+996700123456',
        travel_date='2099-06-01', people_count=2, budget='500 USD for everyone',
        notes='Quiet room')
    session = ChatSession(id='confirmation', client_id=client.id, state=state,
                          revision=1, stage='awaiting_confirmation')
    database.add(session)
    database.commit()
    assert build_preview(database, session)['can_confirm']
    first = confirm_booking(database, session, client.id, 1, True)
    again = confirm_booking(database, session, client.id, 1, True)
    request = database.get(TravelRequest, first['request_id'])
    assert again['request_id'] == first['request_id']
    assert request.name == 'Anna'
    for value in ('Quiet room', '500 USD', 'Lake hotel', 'Minivan'):
        assert value in request.message
    assert session.state == state
    assert database.query(ChatBookingLink).count() == 1


def test_preview_api_exposes_only_contacts(database):
    from mysite.api import chat as route
    client, _ = seed_selection(database)
    state = dict(client_name='Anna', phone='+996700123456', destination='Issyk Kul',
                 travel_date='2099-06-01', people_count=2, budget='500 USD', notes='Quiet room')
    database.add(ChatSession(id='public-preview', client_id=client.id, state=state))
    database.commit()
    app = FastAPI()
    app.include_router(route.chat_router)
    app.dependency_overrides[get_db] = lambda: database
    app.dependency_overrides[route.current_client] = lambda: client
    with TestClient(app) as api:
        result = api.post('/booking/preview', json={'session_id': 'public-preview'}).json()
    assert result['can_confirm']
    assert result['data'] == dict(client_name='Anna', phone='+996700123456')
    assert database.get(ChatSession, 'public-preview').state == state


def test_send_to_manager_phrase_requires_ready_confirmation():
    from mysite.chain.agent import confirmation_allowed
    assert confirmation_allowed('awaiting_confirmation', 'Отправить менеджеру')
    assert not confirmation_allowed('consultation', 'Отправить менеджеру')
    assert not confirmation_allowed('awaiting_confirmation', 'Отправить менеджеру, но нас трое')


def test_selection_welcome_falls_back_when_provider_fails(monkeypatch):
    from mysite.chain import agent

    async def fail(messages):
        raise RuntimeError('Provider unavailable')

    monkeypatch.setattr(agent, 'llm', SimpleNamespace(ainvoke=fail))
    answer = asyncio.run(agent.selection_welcome({}, {'hotel': {'name': 'Lake hotel'}}))
    assert 'Lake hotel' in answer
    assert 'бюджет' in answer


def test_concurrent_selection_start_keeps_only_winning_session(database, monkeypatch):
    from mysite.api import travel_selection as route
    client, selection = seed_selection(database)

    async def competing_welcome(state, details):
        # Another request binds the selection while this request awaits the model.
        database.add(ChatSession(id='winner', client_id=client.id, state=state))
        database.flush()
        selection.session_id = 'winner'
        database.commit()
        return 'Consultation from the losing request'

    monkeypatch.setattr(route, 'selection_welcome', competing_welcome)
    result = asyncio.run(route.start_selection_chat(selection.id, client, database))
    assert result['session_id'] == 'winner'
    assert result['existing']
    assert database.query(ChatSession).count() == 1
    assert database.query(ChatMessage).count() == 0


def test_complete_conversation_exposes_contacts_and_preserves_manager_data(database, monkeypatch):
    from mysite.api import chat_service
    client, selection = seed_selection(database)
    client_id = client.id
    state = dict(tour_id=selection.tour_id, hotel_id=selection.hotel_id,
        transport_id=selection.transport_id, client_name='Anna', phone='+996700123456',
        travel_date='2099-06-01', people_count=2, budget='500 USD', notes='Quiet room')
    database.add(ChatSession(id='conversation', client_id=client_id, state={}))
    database.commit()
    monkeypatch.setattr(chat_service, 'SessionLocal', sessionmaker(bind=database.get_bind()))
    monkeypatch.setattr(chat_service, 'client_by_token', lambda db, token: SimpleNamespace(id=client_id))

    async def reply(*args, **kwargs):
        return 'Do not show this duplicate summary', state, True

    monkeypatch.setattr(chat_service, 'respond', reply)
    preview = asyncio.run(chat_service.process_message('conversation', client_id, 'test', 'Оформить'))
    assert preview['stage'] == 'awaiting_confirmation'
    assert preview['booking_preview']['data'] == dict(client_name='Anna', phone='+996700123456')
    assert preview['answer'] == 'Проверьте заявку:\nИмя: Anna\nТелефон: +996700123456'
    assert database.query(TravelRequest).count() == 0
    sent = asyncio.run(chat_service.process_message('conversation', client_id, 'test', 'Отправить менеджеру'))
    repeated = asyncio.run(chat_service.process_message('conversation', client_id, 'test', 'Отправить менеджеру'))
    assert sent['stage'] == 'submitted'
    assert sent['booking_submitted']['request_id'] == repeated['booking_submitted']['request_id']
    assert sent['answer'].startswith('Заявка отправлена менеджеру')
    assert database.query(TravelRequest).count() == 1
    assert database.query(ChatMessage).count() == 6
    database.expire_all()
    assert database.get(ChatSession, 'conversation').state == state
