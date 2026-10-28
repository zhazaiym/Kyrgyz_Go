import asyncio
from types import SimpleNamespace

import pytest

from mysite.database.chat_models import ChatBookingLink, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import TravelRequest


def start_chat(client, username):
    response = client.post(
        '/chat/auth/register', json={'username': username, 'password': 'StrongPassword123!'}
    )
    assert response.status_code == 201
    token = response.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    identity = client.get('/chat/auth/me', headers=headers).json()['client_id']
    session_id = client.post('/chat/session', headers=headers).json()['session_id']
    return token, identity, session_id


def complete_state():
    return {
        'client_name': 'Approval Guest',
        'phone': '+996700000123',
        'destination': 'Issyk Kul',
        'travel_date': '2099-06-01',
        'people_count': 2,
        'budget': '500 USD',
        'notes': 'Quiet accommodation',
    }


@pytest.mark.parametrize(
    'approval',
    [
        'Да, подтверждаю',
        'Подтверждаю заявку',
        'Yes, confirm',
        'Ооба, ырастайм',
        'Я готова бронировать тур',
        'Я готов бронировать тур',
        'Я готова бронировать туры',
    ],
)
def test_complete_chat_requires_approval_and_shows_in_admin(
    client, admin_headers, monkeypatch, approval
):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'approval_' + str(abs(hash(approval))))

    async def reply(message, state, history, on_chunk=None):
        return 'Please review your request.', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    result = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Давай забронировать')
    )
    assert result['stage'] == 'awaiting_confirmation'
    assert 'Подтверждаете' in result['answer']
    assert 'Quiet accommodation' in result['answer']
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0

    async def unexpected(*args, **kwargs):
        raise AssertionError('Explicit approval must not call AI')

    monkeypatch.setattr(chat_service, 'respond', unexpected)
    submitted = asyncio.run(chat_service.process_message(session_id, identity, token, approval))
    repeated = asyncio.run(chat_service.process_message(session_id, identity, token, approval))
    assert 'Ваши данные переданы менеджеру KYRGYZGO' in submitted['answer']
    assert 'скоро свяжется с вами' in submitted['answer']
    assert (
        submitted['booking_submitted']['request_id'] == repeated['booking_submitted']['request_id']
    )
    request_id = submitted['booking_submitted']['request_id']
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 1
        assert db.get(TravelRequest, request_id).name == 'Approval Guest'

    client.get('/admin/logout')
    assert client.get('/admin/chat-request/list', follow_redirects=False).status_code in (302, 303)
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    page = client.get('/admin/chat-request/list')
    assert page.status_code == 200
    assert 'Approval Guest' in page.text
    details = client.get(f'/admin/chat-request/details/{request_id}')
    assert details.status_code == 200
    for value in [
        'Approval Guest',
        '+996700000123',
        'Issyk Kul',
        '2099-06-01',
        '500 USD',
        'Quiet accommodation',
    ]:
        assert value in details.text
    edited = client.post(
        f'/admin/chat-request/edit/{request_id}',
        data={'status': 'in_progress', 'save': 'Save'},
        follow_redirects=False,
    )
    assert edited.status_code in (302, 303), edited.text
    with SessionLocal() as db:
        assert db.get(TravelRequest, request_id).status.value == 'in_progress'
    client.get('/admin/logout')


@pytest.mark.parametrize(
    'rejection',
    [
        'Нет',
        'пока не отправляйте',
        'Не оформляйте',
        'Я передумал бронировать',
        'No, thanks',
        'Do not send yet',
        'Азыр жөнөтпө',
    ],
)
def test_rejection_returns_to_collecting_without_request(client, monkeypatch, rejection):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'reject_' + str(abs(hash(rejection))))
    with SessionLocal() as db:
        session = db.get(ChatSession, session_id)
        session.state = complete_state()
        session.stage = 'awaiting_confirmation'
        db.commit()

    async def unexpected(*args, **kwargs):
        raise AssertionError('Explicit rejection must not call AI')

    monkeypatch.setattr(chat_service, 'respond', unexpected)
    result = asyncio.run(chat_service.process_message(session_id, identity, token, rejection))
    assert result['stage'] == 'collecting'
    assert 'не отправлена' in result['answer']
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0


def test_generic_yes_without_preview_cannot_submit(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'no_premature_booking')

    async def reply(message, state, history, on_chunk=None):
        return 'What would you like to do?', state, False

    monkeypatch.setattr(chat_service, 'respond', reply)
    result = asyncio.run(chat_service.process_message(session_id, identity, token, 'Да'))
    assert result['stage'] == 'consultation'
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0


def test_bare_yes_after_preview_does_not_submit(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'bare_yes_after_preview')

    async def reply(message, state, history, on_chunk=None):
        return 'Please confirm explicitly.', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    asyncio.run(chat_service.process_message(session_id, identity, token, 'Хочу забронировать'))
    result = asyncio.run(chat_service.process_message(session_id, identity, token, 'Да'))
    assert result['stage'] == 'awaiting_confirmation'
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0


def test_chat_admin_excludes_ordinary_requests(client, admin_headers):
    with SessionLocal() as db:
        ordinary = TravelRequest(name='Ordinary external request', phone='+996700999999')
        db.add(ordinary)
        db.commit()
        request_id = ordinary.id
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    page = client.get('/admin/chat-request/list')
    assert page.status_code == 200
    assert 'Ordinary external request' not in page.text
    assert client.get(f'/admin/chat-request/details/{request_id}').status_code == 404
    assert client.get(f'/admin/chat-request/edit/{request_id}').status_code == 404
    client.get('/admin/logout')


def test_correction_replaces_preview_and_rejects_old_confirmation(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'correct_booking')

    async def reply(message, state, history, on_chunk=None):
        updated = complete_state()
        if message == 'Actually three guests':
            updated['people_count'] = 3
        return 'Review the updated details.', updated, True

    monkeypatch.setattr(chat_service, 'respond', reply)
    original = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Book this trip')
    )
    corrected = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Actually three guests')
    )
    assert corrected['revision'] > original['revision']
    assert corrected['booking_preview']['data']['people_count'] == 3
    headers = {'Authorization': f'Bearer {token}'}
    assert (
        client.post(
            '/booking/confirm',
            headers=headers,
            json={'session_id': session_id, 'revision': original['revision'], 'confirmed': True},
        ).status_code
        == 409
    )
    submitted = client.post(
        '/booking/confirm',
        headers=headers,
        json={'session_id': session_id, 'revision': corrected['revision'], 'confirmed': True},
    )
    assert submitted.status_code == 200
    with SessionLocal() as db:
        assert db.get(TravelRequest, submitted.json()['request_id']).travelers_count == 3


def test_incomplete_request_cannot_be_confirmed(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'incomplete_booking')

    async def reply(message, state, history, on_chunk=None):
        return 'What is your phone number?', {'client_name': 'Incomplete Guest'}, True

    monkeypatch.setattr(chat_service, 'respond', reply)
    result = asyncio.run(chat_service.process_message(session_id, identity, token, 'Book a trip'))
    assert result['stage'] == 'collecting'
    assert result['booking_preview'] is None
    response = client.post(
        '/booking/confirm',
        headers={'Authorization': f'Bearer {token}'},
        json={'session_id': session_id, 'revision': result['revision'], 'confirmed': True},
    )
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0


def test_refusal_invalidates_pending_confirmation(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'refusal_revision')

    async def reply(message, state, history, on_chunk=None):
        return 'Review your request.', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    preview = asyncio.run(chat_service.process_message(session_id, identity, token, 'Book a trip'))
    refused = asyncio.run(chat_service.process_message(session_id, identity, token, 'Нет'))
    assert refused['revision'] > preview['revision']
    response = client.post(
        '/booking/confirm',
        headers={'Authorization': f'Bearer {token}'},
        json={'session_id': session_id, 'revision': preview['revision'], 'confirmed': True},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('client_name', '   '),
        ('phone', 'not provided'),
        ('phone', '123'),
        ('people_count', -2),
        ('people_count', True),
        ('people_count', 'two'),
        ('duration_days', -1),
    ],
)
def test_preview_rejects_invalid_collected_values(field, value):
    from mysite.api.chat_service import build_preview

    state = complete_state()
    state[field] = value
    session = ChatSession(id='validation-only', state=state, revision=1)
    with SessionLocal() as db:
        preview = build_preview(db, session)
    assert not preview['can_confirm']
    assert field in preview['missing_fields']


def test_websocket_booking_reaches_admin_with_collected_data(client, admin_headers, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'socket_booking_admin')

    async def reply(message, state, history, on_chunk=None):
        return 'Проверьте данные перед отправкой.', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    with client.websocket_connect(
        f'/ws/chat/{session_id}', headers={'origin': 'http://localhost:3000'}
    ) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'connected'
        socket.send_json({'type': 'message', 'message': 'Хочу оформить поездку'})
        events = []
        while not events or events[-1]['type'] != 'message_end':
            events.append(socket.receive_json())
        assert any(event['type'] == 'booking_preview' for event in events)
        socket.send_json({'type': 'message', 'message': 'Я готова бронировать туры'})
        while True:
            event = socket.receive_json()
            assert event['type'] != 'error', event
            if event['type'] == 'booking_submitted':
                request_id = event['request_id']
                break

    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    details = client.get(f'/admin/chat-request/details/{request_id}')
    assert details.status_code == 200
    for value in [
        'Approval Guest',
        '+996700000123',
        'Issyk Kul',
        '2099-06-01',
        '500 USD',
        'Quiet accommodation',
    ]:
        assert value in details.text
    client.get('/admin/logout')


def test_incremental_collection_preserves_answers_and_waits_for_confirmation(
    client, admin_headers, monkeypatch
):
    from langchain_core.messages import AIMessageChunk

    from mysite.api import chat_service
    from mysite.chain import agent

    token, identity, session_id = start_chat(client, 'incremental_collection')
    changes = iter(
        [
            agent.Changes(
                destination='Иссык-Куль',
                people_count=2,
                duration_days=3,
                notes='Тихое размещение',
                budget='500 USD',
            ),
            agent.Changes(booking_intent=True),
            agent.Changes(client_name='Анна'),
            agent.Changes(phone='+996700111222'),
            agent.Changes(travel_date='2099-06-01'),
        ]
    )
    replies = iter(
        [
            'Уточним предпочтения для поездки на Иссык-Куль.',
            'Как к вам обращаться?',
            'Анна, какой номер телефона указать для связи?',
            'На какую точную дату планируете поездку?',
            'Данные собраны. Проверьте сводку заявки.',
        ]
    )
    extraction_prompts = []

    async def extract(prompt):
        extraction_prompts.append(prompt)
        return next(changes)

    async def stream(messages):
        yield AIMessageChunk(content=next(replies))

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    results = []
    for message in [
        'Нас двое, хотим на Иссык-Куль на три дня, бюджет 500 USD и тихое жильё',
        'Хочу отправить заявку',
        'Анна',
        '+996700111222',
        '2099-06-01',
    ]:
        results.append(
            asyncio.run(chat_service.process_message(session_id, identity, token, message))
        )
        with SessionLocal() as db:
            assert db.query(ChatBookingLink).filter_by(session_id=session_id).count() == 0

    assert results[0]['stage'] == 'consultation'
    assert results[1]['stage'] == 'collecting'
    assert results[-1]['stage'] == 'awaiting_confirmation'
    assert 'Как к вам обращаться?' in extraction_prompts[2]
    assert 'номер телефона' in extraction_prompts[3]
    preview = results[-1]['booking_preview']
    assert preview['can_confirm']
    assert preview['data']['client_name'] == 'Анна'
    assert preview['data']['people_count'] == 2
    assert 'Я готова бронировать тур' in results[-1]['answer']

    submitted = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Я готова бронировать тур')
    )
    request_id = submitted['booking_submitted']['request_id']
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    details = client.get(f'/admin/chat-request/details/{request_id}')
    assert details.status_code == 200
    for value in [
        'Анна',
        '+996700111222',
        '2099-06-01',
        'Иссык-Куль',
        'Тихое размещение',
        '500 USD',
    ]:
        assert value in details.text
    client.get('/admin/logout')


@pytest.mark.parametrize(
    ('language', 'summary', 'refusal', 'approval', 'submitted_text'),
    [
        ('en', 'Please review your request', 'No', 'I confirm', 'sent to a KYRGYZGO manager'),
        ('ky', 'Өтүнмөнүн маалыматтарын текшериңиз', 'Жок', 'Ырастайм', 'менеджерине жөнөтүлдү'),
        (
            'de',
            'Bitte prüfen Sie Ihre Anfrage',
            'Nicht absenden',
            'Ich bestätige',
            'an das KYRGYZGO-Team gesendet',
        ),
        ('zh', '请核对申请信息', '不发送', '确认提交', '已发送给 KYRGYZGO 客服'),
    ],
)
def test_booking_summary_and_submission_follow_client_language(
    client, monkeypatch, language, summary, refusal, approval, submitted_text
):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'localized_booking_' + language)

    async def reply(message, state, history, on_chunk=None):
        return '', dict(complete_state(), language=language), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    preview = asyncio.run(chat_service.process_message(session_id, identity, token, 'Book a trip'))
    assert summary in preview['answer']
    declined = asyncio.run(chat_service.process_message(session_id, identity, token, refusal))
    assert declined['stage'] == 'collecting'
    asyncio.run(chat_service.process_message(session_id, identity, token, 'Book a trip'))
    submitted = asyncio.run(chat_service.process_message(session_id, identity, token, approval))
    assert submitted['stage'] == 'submitted'
    assert submitted_text in submitted['answer']


def test_server_shows_one_authoritative_preview_and_keeps_followup_answers(client, monkeypatch):
    from mysite.api import chat_service

    token, identity, session_id = start_chat(client, 'single_authoritative_preview')
    emitted = []

    async def emit(text):
        emitted.append(text)

    async def reply(message, state, history, on_chunk=None):
        answer = (
            'Модельная сводка: подтвердите заявку.'
            if message == 'Оформить'
            else 'Подробное объяснение маршрута.'
        )
        if on_chunk:
            await on_chunk(answer)
        return answer, complete_state(), message == 'Оформить'

    monkeypatch.setattr(chat_service, 'respond', reply)
    preview = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Оформить', on_chunk=emit)
    )
    assert 'Модельная сводка' not in preview['answer']
    assert preview['answer'].count('Подтверждаете отправку') == 1
    assert ''.join(emitted) == preview['answer']
    assert preview['booking_preview']['can_confirm']
    followup = asyncio.run(
        chat_service.process_message(session_id, identity, token, 'Уточните маршрут')
    )
    assert followup['answer'] == 'Подробное объяснение маршрута.'
    assert followup['stage'] == 'awaiting_confirmation'
    assert followup['booking_preview'] is None
