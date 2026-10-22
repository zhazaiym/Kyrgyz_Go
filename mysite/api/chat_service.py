"""Chat persistence and preview/confirmation; LLM cannot call booking writes."""
import asyncio
from datetime import date
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from mysite.database.db import SessionLocal
from mysite.database.chat_models import ChatSession, ChatMessage, ChatBookingLink
from mysite.database.models import TravelRequest, RequestStatusChoices, Tour
from mysite.api.chat_auth import client_by_token
from mysite.chain.agent import respond, confirmation_allowed, CONFIRMATION_TEXT

_locks = {}
_lock_users = {}


async def _database_call(function, *args):
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A worker cannot be cancelled; retain the session lock until it closes its DB session.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


def _is_confirmation_text(message):
    normalized = ' '.join(message.casefold().strip().rstrip('.! ').split())
    return normalized == CONFIRMATION_TEXT


def _preview_summary(db, preview):
    data = preview['data']
    tour = db.get(Tour, data['tour_id']) if data.get('tour_id') else None
    choice = tour.title if tour else data.get('destination')
    return (
        '\n\nПроверьте данные заявки:\n'
        f'Тур или направление: {choice}\n'
        + 'Дата поездки: {}\n'.format(data['travel_date'])
        + 'Количество гостей: {}\n'.format(data['people_count'])
        + 'Имя: {}\n'.format(data['client_name'])
        + 'Телефон: {}\n\n'.format(data['phone'])
        + 'Это заявка менеджеру, а не окончательная бронь. '
        + 'Если всё верно, напишите: «Подтверждаю заявку».'
    )

def owned(db, session_id, client_id):
    session = db.get(ChatSession, session_id)
    if not session or session.client_id != client_id:
        raise HTTPException(404, 'Беседа не найдена')
    return session

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
        if confirmation_allowed(s.stage, message) or (
            s.stage == 'submitted' and _is_confirmation_text(message)
        ):
            result = confirm_booking(db, s, client_id, s.revision, True)
            answer = (
                'Заявка №{} передана менеджеру KYRGYZGO. '.format(
                    result['request_id']
                )
                + 'Менеджер свяжется с вами для проверки мест, стоимости '
                + 'и окончательного подтверждения.'
            )
            db.add_all([
                ChatMessage(session_id=s.id, role='user', content=message),
                ChatMessage(session_id=s.id, role='assistant', content=answer),
            ])
            db.commit()
            final = {'answer': answer, 'revision': s.revision,
                     'booking_intent': True, 'stage': 'submitted',
                     'booking_submitted': result}
            return final, None, None
        last = (db.query(ChatMessage).filter(ChatMessage.session_id == s.id)
                .order_by(ChatMessage.id.desc()).first())
        if not last or last.role != 'user' or last.content != message:
            db.add(ChatMessage(session_id=s.id, role='user', content=message))
            db.commit()
        previous = (db.query(ChatMessage).filter(ChatMessage.session_id == s.id)
                    .order_by(ChatMessage.id.desc()).limit(25).all())
        previous.reverse()
        if previous and previous[-1].role == 'user' and previous[-1].content == message:
            previous = previous[:-1]
        original = dict(s.state or {})

    return None, original, previous


def _save_message_response(session_id, client_id, token, answer, updated, original, intent):
    summary = None
    with SessionLocal() as db:
        c = client_by_token(db, token)
        if c.id != client_id:
            raise HTTPException(401, 'Требуется повторный вход')
        s = owned(db, session_id, client_id)
        if updated != original:
            s.state = updated
            s.revision += 1
        preview = build_preview(db, s)
        preview_event = None
        if intent or s.stage in ('collecting', 'awaiting_confirmation'):
            if preview['can_confirm']:
                s.stage = 'awaiting_confirmation'
                preview_event = preview
                summary = _preview_summary(db, preview)
                answer += summary
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
        final, original, previous = await _database_call(
            _prepare_message, session_id, client_id, token, message
        )
        if final is not None:
            if on_chunk is not None:
                await on_chunk(final['answer'])
            return final
        answer, updated, intent = await respond(
            message, original, previous, on_chunk=on_chunk
        )
        result, summary = await _database_call(
            _save_message_response, session_id, client_id, token,
            answer, updated, original, intent
        )
        if summary and on_chunk is not None:
            await on_chunk(summary)
        return result

def build_preview(db, s):
    state = dict(s.state or {})
    missing = [k for k in ('client_name', 'phone', 'people_count', 'travel_date')
               if not state.get(k)]
    if not state.get('tour_id') and not state.get('destination'):
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
    tour_note = ''
    if st.get('tour_id'):
        t = db.get(Tour, st['tour_id'])
        tour_note = f'Тур #{t.id}: {t.title}. '
    notes = (f'Chat Client: KG-{client_id:06d}; session: {s.id}. ' + tour_note
             + f'Бюджет: {st.get("budget") or "не указан"}. Пожелания: {st.get("notes") or "нет"}.')
    obj = TravelRequest(name=st['client_name'], phone=st['phone'], email=st.get('email'),
                        travel_date=date.fromisoformat(st['travel_date']) if st.get('travel_date') else None,
                        duration_days=st.get('duration_days'), travelers_count=st['people_count'],
                        destination=st.get('destination'), message=notes,
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
