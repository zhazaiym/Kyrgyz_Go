"""Chat persistence and preview/confirmation; LLM cannot call booking writes."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date
from functools import partial
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from ML.agent import respond
from mysite.admin.realtime import publish_new_request
from mysite.api.booking_intent import confirmation_allowed, rejection_allowed
from mysite.api.booking_text import booking_text, preview_text
from mysite.api.client_auth import client_by_token
from mysite.api.errors import error_detail
from mysite.api.observability import record_booking_conflict
from mysite.api.resource_limits import ai_capacity
from mysite.api.selected_services import selected_services
from mysite.api.selection_status import linked_request, processing_status
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatBookingLink, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest
from mysite.database.selection_models import TravelSelection
from mysite.database.traveler_validation import validate_travelers_count
from mysite.dates import bishkek_today
from mysite.phone_validation import normalize_phone

_locks = {}
_lock_users = {}


async def _database_call(function, *args, on_cancel=None):
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # A worker cannot be cancelled; retain the session lock until it closes its DB session.
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            error = task.exception()
            if error is None and on_cancel is not None:
                await _database_call(on_cancel, task.result())
        raise


def _discard_prepared_message(session_id, result):
    final, _, _, _, message_id = result
    if final is None:
        _discard_failed_message(session_id, message_id)


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
        raise HTTPException(404, error_detail('not_found'))
    return session


def advance_message_version(db, session):
    current_version = session.message_version
    updated = (
        db.query(ChatSession)
        .filter(ChatSession.id == session.id, ChatSession.message_version == current_version)
        .update({ChatSession.message_version: current_version + 1}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(409, error_detail('conflict'))
    session.message_version = current_version + 1


def discard_pending_message(db, session_id, message_id):
    if message_id is None:
        return
    (
        db.query(ChatMessage)
        .filter(
            ChatMessage.id == message_id,
            ChatMessage.session_id == session_id,
            ChatMessage.role == 'user',
        )
        .delete(synchronize_session=False)
    )
    db.commit()


def _discard_failed_message(session_id, message_id):
    if message_id is None:
        return
    with SessionLocal() as db:
        # A later assistant turn may belong to another worker. Preserve only
        # a reply committed for this exact user message.
        answered = (
            db.query(ChatMessage.id)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.role == 'assistant',
                ChatMessage.reply_to_message_id == message_id,
            )
            .first()
        )
        if answered:
            return
        discard_pending_message(db, session_id, message_id)


@asynccontextmanager
async def session_lock(session_id):
    _lock_users[session_id] = _lock_users.get(session_id, 0) + 1
    lock = _locks.setdefault(session_id, asyncio.Lock())
    try:
        async with lock:
            yield
    finally:
        users = _lock_users.get(session_id, 1) - 1
        if users > 0:
            _lock_users[session_id] = users
        else:
            _lock_users.pop(session_id, None)
            if not lock.locked():
                _locks.pop(session_id, None)


async def process_message(session_id, client_id, token, message, on_chunk=None, image=None):
    if image is not None:
        # History keeps only a marker: the photo itself is never stored.
        message = f'{message}\n[фото]' if message else '[фото]'
    async with session_lock(session_id):
        return await _respond_and_save(session_id, client_id, token, message, on_chunk, image)


def _prepare_message(session_id, client_id, token, message):
    with SessionLocal() as db:
        c = client_by_token(db, token)
        if c.id != client_id:
            raise HTTPException(401, error_detail('authentication_required'))
        s = owned(db, session_id, client_id)
        if rejection_allowed(s.stage, message):
            advance_message_version(db, s)
            s.stage = 'collecting'
            s.revision += 1
            answer = booking_text(s.state or {})['declined']
            db.add_all(
                [
                    ChatMessage(session_id=s.id, role='user', content=message),
                    ChatMessage(session_id=s.id, role='assistant', content=answer),
                ]
            )
            db.commit()
            return (
                {
                    'answer': answer,
                    'revision': s.revision,
                    'booking_intent': False,
                    'stage': s.stage,
                    'booking_preview': None,
                },
                None,
                None,
                None,
                None,
            )
        if confirmation_allowed(s.stage, message) or (
            s.stage == 'submitted' and _is_confirmation_text(message)
        ):
            result = confirm_booking(db, s, client_id, s.revision, True, message=message)
            if result['status'] == 'needs_update':
                return result, None, None, None, None
            answer = booking_text(s.state or {})['submitted'].format(
                request_id=result['request_id']
            )
            db.add_all(
                [
                    ChatMessage(session_id=s.id, role='user', content=message),
                    ChatMessage(session_id=s.id, role='assistant', content=answer),
                ]
            )
            db.commit()
            final = {
                'answer': answer,
                'revision': s.revision,
                'booking_intent': True,
                'stage': 'submitted',
                'booking_submitted': result,
            }
            return final, None, None, None, None
        # Each accepted operation owns its row, including identical concurrent
        # text. A losing worker may remove only that row.
        user_message = ChatMessage(session_id=s.id, role='user', content=message)
        db.add(user_message)
        db.flush()
        user_message_id = user_message.id
        previous = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == s.id)
            .order_by(ChatMessage.id.desc())
            .limit(25)
            .all()
        )
        previous.reverse()
        if previous and previous[-1].role == 'user' and previous[-1].content == message:
            previous = previous[:-1]
        original = dict(s.state or {})
        message_version = s.message_version
        # Commit only after history has loaded successfully. Plain snapshots
        # remain usable after commit expires ORM objects and the session closes.
        previous = [SimpleNamespace(role=item.role, content=item.content) for item in previous]
        db.commit()

    return None, original, previous, message_version, user_message_id


def _save_message_response(
    session_id,
    client_id,
    token,
    expected_message_version,
    user_message_id,
    answer,
    updated,
    original,
    intent,
):
    summary = None
    with SessionLocal() as db:
        c = client_by_token(db, token)
        if c.id != client_id:
            raise HTTPException(401, error_detail('authentication_required'))
        s = owned(db, session_id, client_id)
        if s.message_version != expected_message_version:
            discard_pending_message(db, s.id, user_message_id)
            raise HTTPException(409, error_detail('conflict'))
        try:
            advance_message_version(db, s)
        except HTTPException:
            discard_pending_message(db, session_id, user_message_id)
            raise
        if s.stage == 'submitted' and (updated != original or intent):
            # A sent request is immutable from chat; do not silently change its
            # state or create a second request from a correction.
            updated, intent = original, False
            answer = {
                'ru': 'Заявка уже отправлена. Для исправления данных обратитесь к менеджеру; для новой поездки откройте новый чат.',
                'ky': 'Өтүнмө жөнөтүлгөн. Маалыматты өзгөртүү үчүн менеджерге кайрылыңыз; жаңы сапар үчүн жаңы чат ачыңыз.',
                'en': 'Your request has already been sent. Contact the manager to correct it, or open a new chat for a new trip.',
                'de': 'Ihre Anfrage wurde bereits gesendet. Für Änderungen wenden Sie sich an das Team; für eine neue Reise öffnen Sie einen neuen Chat.',
                'zh': '您的申请已发送。如需修改，请联系工作人员；如需安排新行程，请开启新对话。',
            }.get(
                original.get('language', 'ru'),
                'Your request has already been sent. Contact the manager to correct it.',
            )
        changed = updated != original
        if changed:
            s.state = updated
            s.revision += 1
        preview = build_preview(db, s)
        preview_event = None
        if intent or s.stage == 'awaiting_confirmation' or (s.stage == 'collecting' and changed):
            if preview['complete']:
                if s.stage != 'awaiting_confirmation' or changed or intent:
                    s.stage = 'awaiting_confirmation'
                    preview = build_preview(db, s)
                    preview_event = preview
                    summary = _preview_summary(db, preview)
                    answer = summary
                s.stage = 'awaiting_confirmation'
            else:
                s.stage = 'collecting'
        if not answer.strip():
            raise HTTPException(502, error_detail('service_unavailable'))
        db.add(
            ChatMessage(
                session_id=s.id,
                role='assistant',
                content=answer,
                reply_to_message_id=user_message_id,
            )
        )
        db.commit()
        return {
            'answer': answer,
            'revision': s.revision,
            'booking_intent': bool(intent),
            'stage': s.stage,
            'booking_preview': preview_event,
        }, summary


async def _respond_and_save(session_id, client_id, token, message, on_chunk=None, image=None):
    # Keep each synchronous database phase off the event loop.
    (final, original, previous, message_version, user_message_id) = await _database_call(
        _prepare_message,
        session_id,
        client_id,
        token,
        message,
        on_cancel=partial(_discard_prepared_message, session_id),
    )
    if final is not None:
        if on_chunk is not None:
            await on_chunk(final['answer'])
        return final
    try:
        with ai_capacity():
            photo = {'image': image} if image is not None else {}
            answer, updated, intent = await respond(
                message, original, previous, on_chunk=None, **photo
            )
            if (
                not isinstance(answer, str)
                or len(answer) > 65_536
                or not isinstance(updated, dict)
                or type(intent) is not bool
            ):
                raise HTTPException(502, error_detail('service_unavailable'))
            try:
                state_bytes = json.dumps(updated, allow_nan=False).encode('utf-8')
            except (ValueError, TypeError) as exc:
                raise HTTPException(502, error_detail('service_unavailable')) from exc
            if len(state_bytes) > 32_768:
                raise HTTPException(502, error_detail('service_unavailable'))
        result, summary = await _database_call(
            _save_message_response,
            session_id,
            client_id,
            token,
            message_version,
            user_message_id,
            answer,
            updated,
            original,
            intent,
        )
    except (Exception, asyncio.CancelledError):
        await _database_call(_discard_failed_message, session_id, user_message_id)
        raise
    if on_chunk is not None:
        await on_chunk(summary or result['answer'])
    return result


def build_preview(db, s):
    state = dict(s.state or {})
    services, unavailable = selected_services(db, state)
    state['selected_services'] = services
    name = state.get('client_name')
    phone = state.get('phone')
    people = state.get('people_count')
    duration = state.get('duration_days')
    missing = list(unavailable)
    try:
        state['email'] = optional_email(state.get('email'))
    except ValueError:
        missing.append('valid_email')
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        missing.append('client_name')
    try:
        state['phone'] = normalize_phone(phone)
    except ValueError:
        missing.append('phone')
    try:
        validate_travelers_count(people)
    except ValueError:
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
            if date.fromisoformat(state['travel_date']) < bishkek_today():
                missing.append('future_travel_date')
        except (ValueError, TypeError):
            missing.append('valid_travel_date')
    if state.get('tour_id') and 'valid_tour' not in unavailable:
        tour = db.get(Tour, state['tour_id'])

        if tour and tour.is_active and 'people_count' not in missing:
            try:
                validate_travelers_count(people, tour)
            except ValueError:
                missing.append('people_count')
    return {
        'status': 'draft',
        'session_id': s.id,
        'revision': s.revision,
        'data': state,
        'missing_fields': missing,
        'complete': not missing,
        'can_confirm': not missing and s.stage == 'awaiting_confirmation',
    }


def already_submitted(request_id, client_id):
    return {
        'status': 'already_submitted',
        'request_id': request_id,
        'client_code': f'KG-{client_id:06d}',
    }


def recover_confirmation(db, session, message=None):
    advance_message_version(db, session)
    session.stage = 'collecting'
    session.revision += 1
    preview = build_preview(db, session)
    answer = booking_text(session.state or {})['invalid_preview']
    if message is not None:
        db.add(ChatMessage(session_id=session.id, role='user', content=message))
    db.add(ChatMessage(session_id=session.id, role='assistant', content=answer))
    db.commit()
    return {
        'status': 'needs_update',
        'answer': answer,
        'revision': session.revision,
        'booking_intent': False,
        'stage': session.stage,
        'booking_preview': preview,
    }


def confirm_booking(db, s, client_id, revision, confirmed, *, message=None):
    if not confirmed:
        raise HTTPException(400, error_detail('invalid_request'))

    existing = (
        db.query(ChatBookingLink)
        .filter(ChatBookingLink.session_id == s.id, ChatBookingLink.revision == revision)
        .first()
    )

    if existing:
        return already_submitted(existing.request_id, client_id)

    if s.stage != 'awaiting_confirmation':
        raise HTTPException(409, error_detail('conflict'))

    preview = build_preview(db, s)

    if revision != s.revision:
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict'))
    if preview['missing_fields']:
        return recover_confirmation(db, s, message)

    st = preview['data']

    selection = (
        db.query(TravelSelection)
        .filter(TravelSelection.session_id == s.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if selection and processing_status(selection, linked_request(db, selection)) in (
        'cancelled',
        'completed',
    ):
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict'))
    try:
        advance_message_version(db, s)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise

        existing = (
            db.query(ChatBookingLink)
            .filter(ChatBookingLink.session_id == s.id, ChatBookingLink.revision == revision)
            .first()
        )

        if existing:
            return already_submitted(existing.request_id, client_id)
        record_booking_conflict()
        raise

    tour_note = ''
    destination = st.get('destination')

    if st.get('tour_id'):
        tour = db.get(Tour, st['tour_id'])
        tour_note = f'Тур #{tour.id}: {tour.title}. '
        destination = tour.title

    notes = (
        f'Chat Client: KG-{client_id:06d}; session: {s.id}. '
        + tour_note
        + f'Язык общения: {st.get("language") or "не указан"}. '
        + f'Бюджет: {st.get("budget") or "не указан"}. '
        + f'Пожелания: {st.get("notes") or "нет"}.'
    )

    if st['selected_services']:
        notes += '\nSelected services: ' + '; '.join(
            f'{item["kind"]} #{item["id"]}: {item["name"]}' for item in st['selected_services']
        )

    obj = TravelRequest(
        client_id=client_id,
        name=st['client_name'],
        phone=st['phone'],
        email=st.get('email'),
        travel_date=(date.fromisoformat(st['travel_date']) if st.get('travel_date') else None),
        duration_days=st.get('duration_days'),
        travelers_count=st['people_count'],
        destination=destination,
        message=notes,
        selected_services=st['selected_services'],
        status=RequestStatusChoices.new,
    )

    try:
        db.add(obj)
        db.flush()

        request_id = obj.id

        db.add(
            ChatBookingLink(
                client_id=client_id, session_id=s.id, request_id=request_id, revision=s.revision
            )
        )

        s.stage = 'submitted'

        if selection:
            selection.status = 'in_progress'
        db.commit()
        publish_new_request(obj.id)
    except IntegrityError:
        db.rollback()

        existing = (
            db.query(ChatBookingLink)
            .filter(ChatBookingLink.session_id == s.id, ChatBookingLink.revision == revision)
            .first()
        )

        if existing:
            return already_submitted(existing.request_id, client_id)
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict'))
    return {'status': 'submitted', 'request_id': obj.id, 'client_code': f'KG-{client_id:06d}'}


def _confirm_booking_for_client(session_id, client_id, token, revision, confirmed):
    with SessionLocal() as db:
        client = client_by_token(db, token)
        if client.id != client_id:
            raise HTTPException(401, error_detail('authentication_required'))
        session = owned(db, session_id, client_id)
        return confirm_booking(db, session, client_id, revision, confirmed)


async def confirm_booking_serialized(session_id, client_id, token, revision, confirmed):
    async with session_lock(session_id):
        return await _database_call(
            _confirm_booking_for_client, session_id, client_id, token, revision, confirmed
        )


def _remove_service(session_id, client_id, token, kind):
    with SessionLocal() as db:
        if client_by_token(db, token).id != client_id:
            raise HTTPException(401, error_detail('authentication_required'))
        session = owned(db, session_id, client_id)
        if session.stage == 'submitted':
            raise HTTPException(409, error_detail('conflict'))
        selection = (
            db.query(TravelSelection)
            .filter_by(session_id=session_id, client_id=client_id)
            .with_for_update()
            .first()
        )
        if selection and processing_status(selection, linked_request(db, selection)) in {
            'completed',
            'cancelled',
        }:
            raise HTTPException(409, error_detail('conflict'))
        advance_message_version(db, session)
        state = dict(session.state or {})
        state.pop(f'{kind}_id', None)
        session.state = state
        session.revision += 1
        session.stage = 'awaiting_confirmation'
        if selection:
            setattr(selection, f'{kind}_id', None)
        preview = build_preview(db, session)

        if preview['complete']:
            answer = _preview_summary(db, preview)
        else:
            session.stage = 'collecting'
            answer = booking_text(state)['service_removed']
            preview['can_confirm'] = False
        db.add(ChatMessage(session_id=session_id, role='assistant', content=answer))
        db.commit()
        return {
            'status': 'updated',
            'stage': session.stage,
            'revision': session.revision,
            'answer': answer,
            'booking_preview': preview,
        }


async def remove_optional_service(session_id, client_id, token, kind):
    if kind not in {'hotel', 'transport'}:
        raise HTTPException(422, error_detail('validation_error'))
    async with session_lock(session_id):
        return await _database_call(_remove_service, session_id, client_id, token, kind)
