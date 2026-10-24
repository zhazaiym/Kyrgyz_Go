"""Chat persistence and preview/confirmation; LLM cannot call booking writes."""
import asyncio
import re
from datetime import date
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from mysite.database.db import SessionLocal
from mysite.database.chat_models import ChatSession, ChatMessage, ChatBookingLink
from mysite.database.models import TravelRequest, RequestStatusChoices, Tour
from mysite.api.client_auth import client_by_token
from mysite.api.booking_text import booking_text, preview_text
from mysite.chain.agent import respond, confirmation_allowed, rejection_allowed

_locks = {}
_lock_users = {}


async def _database_call(function, *args):
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A worker cannot be ccancelled; retain the session lock until it closes its DB session.
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            task.exception()
        raise


def _is_confirmation_text(message):
    return confirmation_allowed('awaiting_confirmation', message)


def _preview_summary(db, preview):
    data = preview['data']
    tour = db.get(Tour, data['tour_id']) if data.get('tour_id') else None
    choice = tour.title if tour else data.get('destination')
    return preview_text(data, choice)

def owned(db, session_id, client_id):
    session = db.get(ChatSession, session_id)
    if not session or session.client_id != client_id:
        raise HTTPException(404, 'Беседа не найдена')
    return session


def advance_message_version(db, session):
    current_version = session.message_version
    updated = (db.query(ChatSession)
               .filter(
                   ChatSession.id == session.id,
                   ChatSession.message_version == current_version,
               )
               .update(
                   {ChatSession.message_version: current_version + 1},
                   synchronize_session=False,
               ))
    if updated != 1:
        db.rollback()
        raise HTTPException(
            409,
            'Чат изменился в другом запросе. Обновите историю и повторите сообщение.',
        )
    session.message_version = current_version + 1


def discard_pending_message(db, session_id, message_id):
    if message_id is None:
        return
    (db.query(ChatMessage)
     .filter(
         ChatMessage.id == message_id,
         ChatMessage.session_id == session_id,
         ChatMessage.role == 'user',
     )
     .delete(synchronize_session=False))
    db.commit()


async def process_message(session_id, client_id, token, message, on_chunk=None):
    _lock_users[session_id] = _lock_users.get(session_id, 0) + 1
    try:
        return await _process_message_locked(
            session_id, client_id, token, message, on_chunk=on_chunk
        )
    finally:
        users = _lock_users.get(session_id, 1) - 1
        if users > 0:
            _lock_users[session_id] = users
        else:
            _lock_users.pop(session_id, None)
            lock = _locks.get(session_id)
            if lock is not None and not lock.locked():
                _locks.pop(session_id, None)


def _prepare_message(session_id, client_id, token, message):
    with SessionLocal() as db:
        c = client_by_token(db, token)
        if c.id != client_id:
            raise HTTPException(401, 'Требуется повторный вход')
        s = owned(db, session_id, client_id)
        if rejection_allowed(s.stage, message):
            advance_message_version(db, s)
            s.stage = 'collecting'
            s.revision += 1
            answer = booking_text(s.state or {})['declined']
            db.add_all([
                ChatMessage(session_id=s.id, role='user', content=message),
                ChatMessage(session_id=s.id, role='assistant', content=answer),
            ])
            db.commit()
            return {'answer': answer, 'revision': s.revision,
                    'booking_intent': False, 'stage': s.stage,
                    'booking_preview': None}, None, None, None, None
        if confirmation_allowed(s.stage, message) or (
            s.stage == 'submitted' and _is_confirmation_text(message)
        ):
            result = confirm_booking(db, s, client_id, s.revision, True)
            answer = booking_text(s.state or {})['submitted'].format(request_id=result['request_id'])
            db.add_all([
                ChatMessage(session_id=s.id, role='user', content=message),
                ChatMessage(session_id=s.id, role='assistant', content=answer),
            ])
            db.commit()
            final = {'answer': answer, 'revision': s.revision,
                     'booking_intent': True, 'stage': 'submitted',
                     'booking_submitted': result}
            return final, None, None, None, None
        last = (db.query(ChatMessage).filter(ChatMessage.session_id == s.id)
                .order_by(ChatMessage.id.desc()).first())
        user_message_id = None
        if not last or last.role != 'user' or last.content != message:
            user_message = ChatMessage(
                session_id=s.id, role='user', content=message
            )
            db.add(user_message)
            db.commit()
            user_message_id = user_message.id
        previous = (db.query(ChatMessage).filter(ChatMessage.session_id == s.id)
                    .order_by(ChatMessage.id.desc()).limit(25).all())
        previous.reverse()
        if previous and previous[-1].role == 'user' and previous[-1].content == message:
            previous = previous[:-1]
        original = dict(s.state or {})
        message_version = s.message_version

    return None, original, previous, message_version, user_message_id


def _save_message_response(
    session_id, client_id, token, expected_message_version, user_message_id,
    answer, updated, original, intent,
):
    summary = None
    with SessionLocal() as db:
        c = client_by_token(db, token)
        if c.id != client_id:
            raise HTTPException(401, 'Требуется повторный вход')
        s = owned(db, session_id, client_id)
        if s.message_version != expected_message_version:
            discard_pending_message(db, s.id, user_message_id)
            raise HTTPException(
                409,
                'Чат изменился в другом запросе. Обновите историю и повторите сообщение.',
            )
        try:
            advance_message_version(db, s)
        except HTTPException:
            discard_pending_message(db, session_id, user_message_id)
            raise
        changed = updated != original
        if changed:
            s.state = updated
            s.revision += 1
        preview = build_preview(db, s)
        preview_event = None
        if intent or s.stage in ('collecting', 'awaiting_confirmation'):
            if preview['can_confirm']:
                if s.stage != 'awaiting_confirmation' or changed or intent:
                    preview_event = preview
                    summary = _preview_summary(db, preview)
                    answer = summary
                s.stage = 'awaiting_confirmation'
            else:
                s.stage = 'collecting'
        db.add(ChatMessage(session_id=s.id, role='assistant', content=answer))
        db.commit()
        return {'answer': answer, 'revision': s.revision,
                'booking_intent': bool(intent), 'stage': s.stage,
                'booking_preview': preview_event}, summary



async def _process_message_locked(
    session_id, client_id, token, message, on_chunk=None
):
    # Keep each synchronous database phase off the event loop.
    lock = _locks.setdefault(session_id, asyncio.Lock())
    async with lock:
        final, original, previous, message_version, user_message_id = await _database_call(
            _prepare_message, session_id, client_id, token, message
        )
        if final is not None:
            if on_chunk is not None:
                await on_chunk(final['answer'])
            return final
        answer, updated, intent = await respond(
            message, original, previous, on_chunk=None
        )
        result, summary = await _database_call(
            _save_message_response, session_id, client_id, token,
            message_version, user_message_id,
            answer, updated, original, intent
        )
        if on_chunk is not None:
            await on_chunk(summary or result['answer'])
        return result

def build_preview(db, s):
    state = dict(s.state or {})
    name = state.get('client_name')
    phone = state.get('phone')
    people = state.get('people_count')
    duration = state.get('duration_days')
    missing = []
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        missing.append('client_name')
    if (not isinstance(phone, str) or len(phone) > 50
            or not re.fullmatch(r'\+?[0-9\s().-]+', phone.strip())
            or not 7 <= len(re.sub(r'[^0-9]', '', phone)) <= 15):
        missing.append('phone')
    if type(people) is not int or not 1 <= people <= 2147483647:
        missing.append('people_count')
    if duration is not None and (type(duration) is not int or not 1 <= duration <= 2147483647):
        missing.append('duration_days')
    if not state.get('travel_date'):
        missing.append('travel_date')
    destination = state.get('destination')
    if not state.get('tour_id') and (
        not isinstance(destination, str) or not destination.strip() or len(destination) > 255
    ):
        missing.append('tour_or_destination')
    if state.get('travel_date'):
        try:
            if date.fromisoformat(state['travel_date']) < date.today():
                missing.append('future_travel_date')
        except (ValueError, TypeError):
            missing.append('valid_travel_date')
    if state.get('tour_id'):
        tour = db.get(Tour, state['tour_id'])
        if not tour or not tour.is_active:
            missing.append('valid_tour')
        elif 'people_count' not in missing and (
            people < tour.min_people or (tour.max_people is not None and people > tour.max_people)
        ):
            missing.append('people_count')
    return {'status': 'draft', 'session_id': s.id, 'revision': s.revision,
            'data': state, 'missing_fields': missing, 'can_confirm': not missing}

def confirm_booking(db, s, client_id, revision, confirmed):
    if not confirmed:
        raise HTTPException(400, 'Необходимо явное подтверждение')
    existing = (db.query(ChatBookingLink).filter(ChatBookingLink.session_id == s.id,
                ChatBookingLink.revision == revision).first())
    if existing:
        return {'status': 'already_submitted', 'request_id': existing.request_id,
                'client_code': f'KG-{client_id:06d}'}
    if s.stage != 'awaiting_confirmation':
        raise HTTPException(
            409, 'Сначала получите полную сводку заявки в чате'
        )
    preview = build_preview(db, s)
    if revision != s.revision:
        raise HTTPException(409, 'Данные изменились, запросите новый preview')
    if preview['missing_fields']:
        raise HTTPException(422, detail={'missing_fields': preview['missing_fields']})
    st = preview['data']
    try:
        advance_message_version(db, s)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        existing = (db.query(ChatBookingLink)
                    .filter(
                        ChatBookingLink.session_id == s.id,
                        ChatBookingLink.revision == revision,
                    )
                    .first())
        if existing:
            return {
                'status': 'already_submitted',
                'request_id': existing.request_id,
                'client_code': f'KG-{client_id:06d}',
            }
        raise
    tour_note = ''
    destination = st.get('destination')
    if st.get('tour_id'):
        t = db.get(Tour, st['tour_id'])
        tour_note = f'Тур #{t.id}: {t.title}. '
        destination = t.title
    notes = (f'Chat Client: KG-{client_id:06d}; session: {s.id}. ' + tour_note
             + f'Язык общения: {st.get("language") or "не указан"}. '
             + f'Бюджет: {st.get("budget") or "не указан"}. Пожелания: {st.get("notes") or "нет"}.')
    obj = TravelRequest(name=st['client_name'], phone=st['phone'], email=st.get('email'),
                        travel_date=date.fromisoformat(st['travel_date']) if st.get('travel_date') else None,
                        duration_days=st.get('duration_days'), travelers_count=st['people_count'],
                        destination=destination, message=notes,
                        status=RequestStatusChoices.new)
    try:
        db.add(obj)
        db.flush()
        db.add(ChatBookingLink(client_id=client_id, session_id=s.id, request_id=obj.id, revision=s.revision))
        s.stage = 'submitted'
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (db.query(ChatBookingLink).filter(ChatBookingLink.session_id == s.id,
                    ChatBookingLink.revision == revision).first())
        if existing:
            return {'status': 'already_submitted', 'request_id': existing.request_id,
                    'client_code': f'KG-{client_id:06d}'}
        raise HTTPException(409, 'Конфликт подтверждения заявки')
    return {'status': 'submitted', 'request_id': obj.id, 'client_code': f'KG-{client_id:06d}'}


def _confirm_booking_for_client(session_id, client_id, token, revision, confirmed):
    with SessionLocal() as db:
        client = client_by_token(db, token)
        if client.id != client_id:
            raise HTTPException(401, 'Требуется повторный вход')
        session = owned(db, session_id, client_id)
        return confirm_booking(
            db, session, client_id, revision, confirmed
        )


async def confirm_booking_serialized(
    session_id, client_id, token, revision, confirmed
):
    _lock_users[session_id] = _lock_users.get(session_id, 0) + 1
    lock = _locks.setdefault(session_id, asyncio.Lock())
    try:
        async with lock:
            return await _database_call(
                _confirm_booking_for_client, session_id, client_id, token, revision, confirmed
            )
    finally:
        users = _lock_users.get(session_id, 1) - 1
        if users > 0:
            _lock_users[session_id] = users
        else:
            _lock_users.pop(session_id, None)
            if not lock.locked():
                _locks.pop(session_id, None)
