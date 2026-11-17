"""Regressions for the AI review of 13.11 (tasks A12-A17, A26, A27); the model is replaced."""

import asyncio
import time
from contextlib import ExitStack
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app
from ML.agent import SHOWN
from ML.errors import AIError
from mysite.api import chat_images, chat_service, chat_ws, guest_ai, rate_limit, resource_limits
from mysite.api.client_auth import SessionExpired, login_required
from mysite.api.errors import error_detail
from mysite.api.observability import render_metrics
from mysite.database.chat_models import ChatLoginToken, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import Tour, TravelRequest
from mysite.database.token_utils import digest, utcnow
from tests.test_chat_booking_flow import complete_state, start_chat
from tests.test_chat_images import chat, jpeg_with_gps, upload

ORIGIN = {'origin': 'http://localhost:3000'}


def new_session(client, token):
    response = client.post('/chat/session', headers={'Authorization': f'Bearer {token}'})
    return response.json()['session_id']


# A12 --------------------------------------------------------------------------------------


def test_one_client_cannot_take_every_model_place(client, monkeypatch):
    token, identity, first = start_chat(client, 'a12_greedy')
    sessions = [first] + [new_session(client, token) for _ in range(4)]
    other_token, other_identity, other_session = start_chat(client, 'a12_patient')

    async def scenario():
        release = asyncio.Event()
        running = []

        async def slow(message, state, history, on_chunk=None):
            running.append(message)
            if message == 'greedy':
                await release.wait()
            return 'Answer', state, False

        monkeypatch.setattr(chat_service, 'respond', slow)
        greedy = [
            asyncio.create_task(chat_service.process_message(sid, identity, token, 'greedy'))
            for sid in sessions
        ]
        # Five conversations at once: two write, the rest are refused without waiting.
        for _ in range(100):
            refused = [task for task in greedy if task.done()]
            if len(refused) == 3:
                break
            await asyncio.sleep(0.05)
        assert len(refused) == 3 and running.count('greedy') == 2
        for task in refused:
            assert task.exception().status_code == 503
        # Two of the four places stay free for everyone else.
        answer = await asyncio.wait_for(
            chat_service.process_message(other_session, other_identity, other_token, 'patient'),
            timeout=10,
        )
        assert answer['answer'] == 'Answer'
        release.set()
        await asyncio.gather(*greedy, return_exceptions=True)

    asyncio.run(scenario())
    assert resource_limits._ai_active == 0 and not resource_limits._ai_owners
    with SessionLocal() as db:
        # A refused message leaves no unanswered turn in the history.
        left = db.query(ChatMessage).filter(
            ChatMessage.session_id.in_(sessions), ChatMessage.role == 'user'
        )
        assert left.count() == 2


def test_busy_model_is_awaited_briefly_instead_of_an_instant_refusal(client, monkeypatch):
    first_token, first_identity, first_session = start_chat(client, 'a12_queue_first')
    second_token, second_identity, second_session = start_chat(client, 'a12_queue_second')
    monkeypatch.setenv('AI_MAX_CONCURRENT', '1')

    async def scenario():
        async def brief(message, state, history, on_chunk=None):
            await asyncio.sleep(0.3)
            return 'Answer', state, False

        monkeypatch.setattr(chat_service, 'respond', brief)
        results = await asyncio.gather(
            chat_service.process_message(first_session, first_identity, first_token, 'one'),
            chat_service.process_message(second_session, second_identity, second_token, 'two'),
        )
        assert [result['answer'] for result in results] == ['Answer', 'Answer']

        async def stuck(message, state, history, on_chunk=None):
            await asyncio.sleep(3)
            return 'Answer', state, False

        monkeypatch.setattr(chat_service, 'respond', stuck)
        monkeypatch.setenv('AI_QUEUE_SECONDS', '1')
        resource_limits.setting.cache_clear()
        holder = asyncio.create_task(
            chat_service.process_message(first_session, first_identity, first_token, 'three')
        )
        await asyncio.sleep(0.2)
        with pytest.raises(HTTPException) as busy:
            await chat_service.process_message(
                second_session, second_identity, second_token, 'four'
            )
        assert busy.value.status_code == 503
        holder.cancel()
        await asyncio.gather(holder, return_exceptions=True)

    asyncio.run(scenario())
    assert resource_limits._ai_active == 0 and not resource_limits._ai_waiters


# A13 --------------------------------------------------------------------------------------


def spending(tokens, calls):
    async def reply(message, state, history, on_chunk=None):
        calls.append(message)
        chat_service._count_tokens('generation', tokens)
        return 'Answer', state, False

    return reply


def test_common_daily_token_budget_stops_the_chat_until_the_next_day(client, monkeypatch, caplog):
    token, identity, session_id = start_chat(client, 'a13_spender')
    other_token, other_identity, other_session = start_chat(client, 'a13_newcomer')
    day = (int(time.time()) // 86_400 + 2) * 86_400
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: day)
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('AI_DAILY_TOKENS', '1000')
    calls = []
    monkeypatch.setattr(chat_service, 'respond', spending(850, calls))

    def send(session, client_id, client_token, text):
        return asyncio.run(chat_service.process_message(session, client_id, client_token, text))

    with caplog.at_level('WARNING', logger='mysite.api.rate_limit'):
        send(session_id, identity, token, 'first')
        send(session_id, identity, token, 'second')
    assert '80% spent' in caplog.text and 'budget for today is spent' in caplog.text

    with pytest.raises(AIError) as refused:
        send(other_session, other_identity, other_token, 'third')
    assert refused.value.code == 'ai_rate_limit'
    assert 'Лимит AI' in refused.value.message
    assert calls == ['first', 'second']  # the model was not called
    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=other_session, role='user').count() == 0
    assert 'kerben_ai_tokens_total{operation="generation"}' in render_metrics()

    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: day + 86_400)
    assert send(other_session, other_identity, other_token, 'next day')['answer'] == 'Answer'


def test_client_and_address_budgets_do_not_stop_other_clients(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a13_one_client')
    twin_token, twin_identity, twin_session = start_chat(client, 'a13_same_address')
    other_token, other_identity, other_session = start_chat(client, 'a13_other_address')
    day = (int(time.time()) // 86_400 + 5) * 86_400
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: day)
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setenv('AI_CLIENT_DAILY_TOKENS', '1000')
    monkeypatch.setenv('AI_IP_DAILY_TOKENS', '1500')
    calls = []
    monkeypatch.setattr(chat_service, 'respond', spending(1000, calls))

    def send(session, client_id, client_token, text, network):
        return asyncio.run(
            chat_service.process_message(session, client_id, client_token, text, network=network)
        )

    send(session_id, identity, token, 'first', '198.51.100.7')
    with pytest.raises(HTTPException) as own:
        send(session_id, identity, token, 'second', '198.51.100.7')
    assert own.value.status_code == 429 and own.value.detail['code'] == 'rate_limited'
    # A second account from the same address shares the address budget.
    send(twin_session, twin_identity, twin_token, 'third', '198.51.100.7')
    third_token, third_identity, third_session = start_chat(client, 'a13_third_account')
    with pytest.raises(HTTPException) as address:
        send(third_session, third_identity, third_token, 'fourth', '198.51.100.7')
    assert address.value.status_code == 429
    assert send(other_session, other_identity, other_token, 'fifth', '203.0.113.9')['answer']
    assert calls == ['first', 'third', 'fifth']


def test_tokens_of_a_failed_reply_are_still_charged(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a13_failed_reply')
    charged = []
    monkeypatch.setattr(chat_service, 'record_ai_spend', lambda *args: charged.append(args))

    async def failing(message, state, history, on_chunk=None):
        chat_service._count_tokens('extractor', 250)
        raise AIError('ai_unavailable')

    monkeypatch.setattr(chat_service, 'respond', failing)
    with pytest.raises(AIError):
        asyncio.run(
            chat_service.process_message(session_id, identity, token, 'x', network='192.0.2.1')
        )
    assert charged == [(identity, '192.0.2.1', 250)]


# A14 --------------------------------------------------------------------------------------


def test_one_address_cannot_use_up_the_guest_limit_for_everyone(monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            return SimpleNamespace(content='Travel advice')

    original = guest_ai.enforce_rate_limit
    suffix = uuid4().hex[:8]
    counted = []

    def quota(scope, principal, **kwargs):
        counted.append(scope)
        return original(scope + suffix, principal, **kwargs)

    hour = (int(time.time()) // 3600 + 3) * 3600
    clock = {'now': hour}
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: clock['now'])
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'true')
    monkeypatch.setattr(guest_ai, 'enforce_rate_limit', quota)
    monkeypatch.setattr(guest_ai, 'client', lambda kind: Model())
    question = {'context': {'people': 2}}
    with TestClient(app, client=('192.0.2.61', 51000)) as greedy:
        for minute in range(2):
            clock['now'] = hour + minute * 60
            for _ in range(5):
                assert greedy.post('/api/ask-ai', json=question).status_code == 200
        clock['now'] = hour + 180
        counted.clear()
        limited = greedy.post('/api/ask-ai', json=question)
        assert limited.status_code == 429
        # The address stopped at its own hourly share; the common counter was not touched.
        assert 'guest-ai-global' not in counted
    with TestClient(app, client=('192.0.2.62', 51000)) as visitor:
        assert visitor.post('/api/ask-ai', json=question).status_code == 200


def test_busy_model_does_not_count_against_the_guest_limits(monkeypatch):
    counted = []
    monkeypatch.setattr(
        guest_ai, 'enforce_rate_limit', lambda *args, **kwargs: counted.append(args)
    )
    monkeypatch.setattr(guest_ai, 'client', lambda kind: pytest.fail('Provider called'))
    monkeypatch.setenv('AI_QUEUE_SECONDS', '1')
    resource_limits.setting.cache_clear()
    monkeypatch.setattr(resource_limits, '_ai_active', resource_limits.setting('AI_MAX_CONCURRENT'))
    with TestClient(app, client=('192.0.2.63', 51000)) as http:
        assert http.post('/api/ask-ai', json={'context': {'people': 2}}).status_code == 503
    assert counted == []


# A15 --------------------------------------------------------------------------------------


def active_websockets():
    line = next(
        line
        for line in render_metrics().splitlines()
        if line.startswith('kerben_websocket_connections_active')
    )
    return float(line.split()[-1])


def connect(client, session_id, token):
    websocket = client.websocket_connect(f'/ws/chat/{session_id}', headers=ORIGIN)
    websocket.__enter__()
    websocket.send_json({'type': 'auth', 'token': token})
    return websocket


def test_silent_connection_is_closed_and_frees_its_place(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a15_silent')
    monkeypatch.setenv('WS_IDLE_SECONDS', '1')
    before = active_websockets()
    with client.websocket_connect(f'/ws/chat/{session_id}', headers=ORIGIN) as websocket:
        websocket.send_json({'type': 'auth', 'token': token})
        assert websocket.receive_json()['type'] == 'connected'
        assert active_websockets() == before + 1
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert (closed.value.code, closed.value.reason) == (1000, 'idle')
    assert active_websockets() == before
    assert identity not in chat_ws._client_connections


def test_connection_that_never_logs_in_is_closed(client, monkeypatch):
    _, _, session_id = start_chat(client, 'a15_no_login')
    monkeypatch.setenv('WS_AUTH_SECONDS', '1')
    with client.websocket_connect(f'/ws/chat/{session_id}', headers=ORIGIN) as websocket:
        assert websocket.receive_json()['code'] == 'authentication_failed'
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_ninth_connection_of_one_client_is_refused(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a15_many_tabs')
    monkeypatch.setenv('WS_MAX_PER_IP', '16')
    monkeypatch.setenv('WS_MAX_PER_CLIENT', '8')
    before = active_websockets()
    with ExitStack() as stack:
        for _ in range(8):
            websocket = connect(client, session_id, token)
            stack.callback(websocket.__exit__, None, None, None)
            assert websocket.receive_json()['type'] == 'connected'
        ninth = connect(client, session_id, token)
        stack.callback(ninth.__exit__, None, None, None)
        assert ninth.receive_json()['code'] == 'too_many_connections'
        with pytest.raises(WebSocketDisconnect) as refused:
            ninth.receive_json()
        assert refused.value.code == 1008
        assert chat_ws._client_connections[identity] == 8
    assert identity not in chat_ws._client_connections
    assert active_websockets() == before
    # After the tabs are closed the client connects again.
    with client.websocket_connect(f'/ws/chat/{session_id}', headers=ORIGIN) as websocket:
        websocket.send_json({'type': 'auth', 'token': token})
        assert websocket.receive_json()['type'] == 'connected'


# A16 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('error', 'code', 'close'),
    [
        (HTTPException(404, error_detail('not_found')), 'session_not_found', True),
        (SessionExpired(), 'session_expired', True),
        (login_required('Недействительный токен входа'), 'authentication_failed', True),
        (HTTPException(403, error_detail('forbidden')), 'authentication_failed', True),
        (HTTPException(409, error_detail('conflict')), 'booking_conflict', False),
        (HTTPException(503, error_detail('service_unavailable')), 'ai_busy', False),
        (HTTPException(502, error_detail('service_unavailable')), 'request_invalid', False),
        (HTTPException(400, error_detail('invalid_request')), 'request_invalid', False),
        (HTTPException(422, 'plain text detail'), 'request_invalid', False),
        (HTTPException(400, {'code': 'odd', 'payload': [1]}), 'request_invalid', False),
    ],
)
def test_websocket_error_text_is_never_a_python_dictionary(error, code, close):
    public_code, message, must_close = chat_ws.public_http_error(error)
    assert (public_code, must_close) == (code, close)
    assert message and '{' not in message and "'code'" not in message


def test_conflict_reaches_the_chat_as_readable_text(client, monkeypatch):
    token, _, session_id = start_chat(client, 'a16_conflict')

    async def conflicting(*args, **kwargs):
        # What the service raises when two messages of one conversation collide.
        raise HTTPException(409, error_detail('conflict'))

    monkeypatch.setattr(chat_ws, 'process_message', conflicting)
    (reply,) = chat(client, token, session_id, [{'type': 'message', 'message': 'Два сообщения'}])
    assert reply == {
        'type': 'error',
        'code': 'booking_conflict',
        'message': 'Действие недоступно в текущем состоянии',
    }


def test_expired_login_is_told_apart_from_an_unknown_token_without_reading_text(client):
    token, _, session_id = start_chat(client, 'a16_expired')
    with SessionLocal() as db:
        access = db.query(ChatLoginToken).filter_by(token_hash=digest(token)).one()
        access.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    codes = []
    for candidate in (token, 'unknown-token'):
        with client.websocket_connect(f'/ws/chat/{session_id}', headers=ORIGIN) as websocket:
            websocket.send_json({'type': 'auth', 'token': candidate})
            codes.append(websocket.receive_json()['code'])
    assert codes == ['session_expired', 'authentication_failed']
    # The HTTP answer keeps its code for the frontend.
    response = client.get('/chat/sessions', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'authentication_required'


# A17 --------------------------------------------------------------------------------------


def test_photo_survives_a_failed_reply_and_is_used_up_by_a_saved_one(client, monkeypatch):
    chat_images._pending.clear()
    token, _, session_id = start_chat(client, 'a17_photo_retry')
    attempts = []

    async def flaky(message, state, history, on_chunk=None, image=None):
        attempts.append(image)
        if len(attempts) == 1:
            raise AIError('ai_unavailable')
        return 'Похожий тур есть.', state, False

    monkeypatch.setattr(chat_service, 'respond', flaky)
    image_id = upload(client, token, session_id, jpeg_with_gps()).json()['image_id']
    frame = {'type': 'message', 'message': 'Хочу сюда', 'image_id': image_id}

    failed, repeated, again = chat(client, token, session_id, [frame, frame, frame])

    assert failed['code'] == 'ai_unavailable'
    assert repeated['type'] == 'message_end'
    assert again['code'] == 'image_not_found'
    assert attempts[0] == attempts[1] and attempts[0] is not None
    assert chat_images._pending == {} and not chat_images._in_use


# A26 --------------------------------------------------------------------------------------


def one_day_tour():
    with SessionLocal() as db:
        tour = Tour(title=f'Башня Бурана {uuid4().hex[:6]}', price=65, duration_days=1)
        db.add(tour)
        db.commit()
        return tour.id, tour.title


def test_ready_tour_gives_its_own_length_to_the_summary_and_the_request(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a26_duration')
    tour_id, title = one_day_tour()
    state = {**complete_state(), 'tour_id': tour_id, 'duration_days': 12}
    state.pop('destination')

    async def reply(message, state_before, history, on_chunk=None):
        return 'Проверьте заявку.', state, True

    monkeypatch.setattr(chat_service, 'respond', reply)
    summary = asyncio.run(chat_service.process_message(session_id, identity, token, 'Оформите'))
    assert summary['booking_preview']['data']['duration_days'] == 1
    assert 'Продолжительность (дней): 1\n' in summary['answer'] and title in summary['answer']

    sent = asyncio.run(chat_service.process_message(session_id, identity, token, 'Подтверждаю'))
    with SessionLocal() as db:
        request = db.get(TravelRequest, sent['booking_submitted']['request_id'])
        assert (request.duration_days, request.destination) == (1, title)


# A27 --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'model_text',
    [
        'Все данные получены. Напишите «Подтверждаю», чтобы отправить заявку.',
        'Спасибо! Записал телефон.',
    ],
)
def test_collected_request_gets_the_server_summary_and_one_confirmation(
    client, monkeypatch, model_text
):
    token, identity, session_id = start_chat(client, 'a27_' + uuid4().hex[:8])
    shown = [{'kind': 'tour', 'id': 54, 'title': 'Башня Бурана'}]

    async def reply(message, state, history, on_chunk=None):
        # The extraction reports no booking intent: the client only gave the last field.
        return model_text, {**complete_state(), SHOWN: shown}, False

    monkeypatch.setattr(chat_service, 'respond', reply)
    summary = asyncio.run(
        chat_service.process_message(session_id, identity, token, '+996700000123')
    )
    assert summary['stage'] == 'awaiting_confirmation'
    assert summary['answer'].lstrip().startswith('Проверьте данные заявки:')
    assert summary['answer'].count('«Подтверждаю»') == 1
    # The list of shown records is the server's own note: not in the summary data.
    assert SHOWN not in summary['booking_preview']['data']
    with SessionLocal() as db:
        assert db.get(ChatSession, session_id).state[SHOWN] == shown

    async def unexpected(*args, **kwargs):
        raise AssertionError('The confirmation must not reach the model')

    monkeypatch.setattr(chat_service, 'respond', unexpected)
    sent = asyncio.run(chat_service.process_message(session_id, identity, token, 'Подтверждаю'))
    assert sent['stage'] == 'submitted' and sent['booking_submitted']['status'] == 'submitted'


def test_model_asking_to_confirm_before_the_data_is_complete_is_replaced(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a27_early_ask')
    partial = {'destination': 'Issyk Kul', 'people_count': 2}

    async def reply(message, state, history, on_chunk=None):
        return 'Отлично! Напишите «Подтверждаю».', partial, False

    monkeypatch.setattr(chat_service, 'respond', reply)
    result = asyncio.run(chat_service.process_message(session_id, identity, token, 'Нас двое'))
    assert result['stage'] == 'collecting'
    assert '«Подтверждаю»' not in result['answer']
    assert 'не хватает данных' in result['answer'] and 'телефон' in result['answer']


def test_shown_records_alone_do_not_count_as_a_change_of_the_request(client, monkeypatch):
    token, identity, session_id = start_chat(client, 'a25_shown_only')

    async def reply(message, state, history, on_chunk=None):
        return (
            'Есть два тура.',
            {**state, SHOWN: [{'kind': 'tour', 'id': 1, 'title': 'Тур'}]},
            False,
        )

    monkeypatch.setattr(chat_service, 'respond', reply)
    result = asyncio.run(chat_service.process_message(session_id, identity, token, 'Что есть?'))
    assert (result['revision'], result['stage'], result['answer']) == (
        0,
        'consultation',
        'Есть два тура.',
    )
    with SessionLocal() as db:
        assert db.get(ChatSession, session_id).state == {
            SHOWN: [{'kind': 'tour', 'id': 1, 'title': 'Тур'}]
        }
