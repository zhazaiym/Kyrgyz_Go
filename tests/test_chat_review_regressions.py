import asyncio
from datetime import datetime, timezone

from mysite.api import chat_service
from mysite.database.chat_models import ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import TravelRequest
from tests.test_chat_booking_flow import complete_state, start_chat


def test_chat_request_is_visible_and_cancellable_by_its_owner(client, monkeypatch):
    token, identity, sid = start_chat(client, 'review_request_owner')

    async def reply(message, state, history, on_chunk=None):
        return 'Review request', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    asyncio.run(chat_service.process_message(sid, identity, token, 'Оформить заявку'))
    result = asyncio.run(chat_service.process_message(sid, identity, token, 'Подтверждаю заявку'))
    request_id = result['booking_submitted']['request_id']
    headers = {'Authorization': 'Bearer ' + token}
    with SessionLocal() as db:
        assert db.get(TravelRequest, request_id).client_id == identity
    mine = client.get('/travel-requests/me/', headers=headers)
    assert mine.status_code == 200
    assert request_id in [item['id'] for item in mine.json()]
    cancelled = client.delete(f'/travel-requests/me/{request_id}/', headers=headers)
    assert cancelled.status_code == 200
    with SessionLocal() as db:
        assert db.get(TravelRequest, request_id).status.value == 'cancelled'


def test_question_after_declining_preview_keeps_answer_and_requires_fresh_intent(
    client, monkeypatch
):
    token, identity, sid = start_chat(client, 'review_declined_question')
    with SessionLocal() as db:
        session = db.get(ChatSession, sid)
        session.state = complete_state()
        session.stage = 'awaiting_confirmation'
        db.commit()

    async def reply(message, state, history, on_chunk=None):
        return 'Подробный ответ о маршруте.', dict(state), False

    monkeypatch.setattr(chat_service, 'respond', reply)
    asyncio.run(chat_service.process_message(sid, identity, token, 'Нет'))
    result = asyncio.run(
        chat_service.process_message(sid, identity, token, 'Как проходит маршрут?')
    )
    assert result['answer'] == 'Подробный ответ о маршруте.'
    assert result['stage'] == 'collecting'
    assert not result.get('booking_preview')


def test_bishkek_date_is_already_tomorrow_before_utc_midnight():
    from mysite.dates import bishkek_today

    assert bishkek_today(datetime(2026, 11, 6, 21, tzinfo=timezone.utc)).isoformat() == '2026-11-07'
