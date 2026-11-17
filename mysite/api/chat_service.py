"""Chat persistence and preview/confirmation; LLM cannot call booking writes."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import date
from functools import partial
from types import SimpleNamespace
from typing import NamedTuple

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ML import runtime as agent_runtime
from ML.agent import client_state, respond
from mysite.admin.realtime import publish_new_request
from mysite.api.booking_intent import confirmation_allowed, explicit_confirmation, rejection_allowed
from mysite.api.booking_text import booking_text, not_ready_text, preview_text
from mysite.api.client_auth import client_by_token
from mysite.api.errors import error_detail
from mysite.api.observability import record_ai_call, record_ai_tokens, record_booking_conflict
from mysite.api.rate_limit import enforce_ai_budget, record_ai_spend
from mysite.api.resource_limits import ai_capacity
from mysite.api.selected_services import selected_services
from mysite.api.selection_status import linked_request, processing_status
from mysite.database import models as catalogue_models
from mysite.database.booking_validation import optional_email
from mysite.database.chat_models import ChatBookingLink, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest
from mysite.database.selection_models import TravelSelection
from mysite.database.traveler_validation import validate_travelers_count
from mysite.dates import bishkek_today
from mysite.phone_validation import normalize_phone

log = logging.getLogger(__name__)
_locks = {}
_lock_users = {}
_spent_tokens = ContextVar('chat_spent_tokens', default=None)


def _count_tokens(operation, tokens):
    record_ai_tokens(operation, tokens)
    spent = _spent_tokens.get()
    if spent is not None:
        spent.append(tokens)


# The agent imports nothing from the application: this is all it is lent.
agent_runtime.configure(
    sessions=lambda: SessionLocal(),
    models=catalogue_models,
    today=bishkek_today,
    record_ai_call=record_ai_call,
    record_ai_tokens=_count_tokens,
)


class ServerReply(NamedTuple):
    """The server answered this turn itself; the model is not needed."""

    result: dict


class ModelTurn(NamedTuple):
    """The client's message is stored and waits for the model's reply."""

    state: dict
    history: list
    message_version: int
    message_id: int


class ReplyStream:
    """Reply text sent to the client piece by piece while the model writes it.

    ``reset()`` withdraws everything sent so far, for text that will not be
    kept: a preamble before a tool call, a cut-off answer, or a reply the
    server replaces with its own (booking summary, error).
    """

    def __init__(self, send, withdraw):
        self._send = send
        self._withdraw = withdraw
        self.text = ''

    async def __call__(self, text):
        if text:
            self.text += text
            await self._send(text)

    async def reset(self):
        if self.text:
            self.text = ''
            await self._withdraw()

    async def finish(self, final):
        """Make the client show exactly ``final``, keeping what is already there."""
        if self.text.strip() != final.strip():
            await self.reset()
            await self(final)


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


def _discard_prepared_message(session_id, prepared):
    if isinstance(prepared, ModelTurn):
        _discard_failed_message(session_id, prepared.message_id)


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


def _client_session(db, session_id, client_id, token):
    """The client's own conversation, with the login checked again."""
    if client_by_token(db, token).id != client_id:
        raise HTTPException(401, error_detail('authentication_required'))
    return owned(db, session_id, client_id)


def _store_turn(db, chat, message, answer):
    db.add_all(
        [
            ChatMessage(session_id=chat.id, role='user', content=message),
            ChatMessage(session_id=chat.id, role='assistant', content=answer),
        ]
    )
    db.commit()


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


async def process_message(
    session_id, client_id, token, message, on_chunk=None, image=None, network=None
):
    if image is not None:
        # History keeps only a marker: the photo itself is never stored.
        message = f'{message}\n[фото]' if message else '[фото]'
    async with session_lock(session_id):
        return await _respond_and_save(
            session_id, client_id, token, message, on_chunk, image, network
        )


def _decline(db, chat, message):
    advance_message_version(db, chat)
    chat.stage = 'collecting'
    chat.revision += 1
    answer = booking_text(chat.state or {})['declined']
    _store_turn(db, chat, message, answer)
    return {
        'answer': answer,
        'revision': chat.revision,
        'booking_intent': False,
        'stage': chat.stage,
        'booking_preview': None,
    }


def _submit(db, chat, client_id, message):
    result = confirm_booking(db, chat, client_id, chat.revision, True, message=message)
    if result['status'] == 'needs_update':
        return result
    answer = booking_text(chat.state or {})['submitted'].format(request_id=result['request_id'])
    _store_turn(db, chat, message, answer)
    return {
        'answer': answer,
        'revision': chat.revision,
        'booking_intent': True,
        'stage': 'submitted',
        'booking_submitted': result,
    }


def _server_reply(db, chat, client_id, message):
    """The server's own answer to a refusal or a confirmation; None when the model replies."""
    if rejection_allowed(chat.stage, message):
        return _decline(db, chat, message)
    if confirmation_allowed(chat.stage, message) or (
        chat.stage == 'submitted' and _is_confirmation_text(message)
    ):
        return _submit(db, chat, client_id, message)
    if (
        chat.stage in ('consultation', 'collecting')
        and explicit_confirmation(message)
        and (
            chat.stage == 'collecting'
            or build_preview(db, chat)['complete']
            or _assistant_asked_to_confirm(db, chat)
        )
    ):
        # The client confirms before any server summary, often after the AI
        # paraphrased one. The AI must not answer this: show the real
        # summary, or say exactly what is still missing. A first "book it"
        # with nothing collected yet still goes to the AI.
        return _confirmation_before_summary(db, chat, message)
    return None


def _prepare_message(session_id, client_id, token, message):
    with SessionLocal() as db:
        chat = _client_session(db, session_id, client_id, token)
        answered = _server_reply(db, chat, client_id, message)
        if answered is not None:
            return ServerReply(answered)
        # Each accepted operation owns its row, including identical concurrent
        # text. A losing worker may remove only that row.
        user_message = ChatMessage(session_id=chat.id, role='user', content=message)
        db.add(user_message)
        db.flush()
        user_message_id = user_message.id
        previous = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == chat.id)
            .order_by(ChatMessage.id.desc())
            .limit(25)
            .all()
        )
        previous.reverse()
        if previous and previous[-1].role == 'user' and previous[-1].content == message:
            previous = previous[:-1]
        original = dict(chat.state or {})
        message_version = chat.message_version
        # Commit only after history has loaded successfully. Plain snapshots
        # remain usable after commit expires ORM objects and the session closes.
        previous = [SimpleNamespace(role=item.role, content=item.content) for item in previous]
        db.commit()

    return ModelTurn(original, previous, message_version, user_message_id)


CONFIRM_PROMPTS = ('«подтверждаю»', 'i confirm', '«ырастайм»', 'ich bestätige', '确认提交')


def _last_assistant_text(db, chat):
    last = (
        db.query(ChatMessage.content)
        .filter(ChatMessage.session_id == chat.id, ChatMessage.role == 'assistant')
        .order_by(ChatMessage.id.desc())
        .first()
    )
    return last[0] if last else ''


def _asks_to_confirm(text):
    text = text.casefold()
    return any(prompt in text for prompt in CONFIRM_PROMPTS)


def _assistant_asked_to_confirm(db, chat):
    return _asks_to_confirm(_last_assistant_text(db, chat))


def _confirmation_before_summary(db, chat, message):
    advance_message_version(db, chat)
    preview = build_preview(db, chat)
    if preview['complete']:
        chat.stage = 'awaiting_confirmation'
        preview = build_preview(db, chat)
        answer = _preview_summary(db, preview)
    else:
        chat.stage = 'collecting'
        answer = not_ready_text(chat.state or {}, preview['missing_fields'])
    _store_turn(db, chat, message, answer)
    return {
        'answer': answer,
        'revision': chat.revision,
        'booking_intent': True,
        'stage': chat.stage,
        'booking_preview': preview,
    }


def _booking_step(db, chat, answer, changed, intent):
    """Move the stage after a model reply; the reply and the summary event to send.

    Only the server asks for the confirmation word, and only under its own
    summary: a model reply that asks for it is replaced.
    """
    preview = build_preview(db, chat)
    asked = _asks_to_confirm(answer)
    if chat.stage == 'submitted' or not (
        intent
        or asked
        or chat.stage == 'awaiting_confirmation'
        or (changed and (chat.stage == 'collecting' or preview['complete']))
    ):
        return answer, None
    if not preview['complete']:
        chat.stage = 'collecting'
        if asked or answer.strip() == _last_assistant_text(db, chat).strip():
            # The model asked to confirm too early or echoed its previous turn;
            # name the missing fields deterministically.
            answer = not_ready_text(chat.state or {}, preview['missing_fields'])
        return answer, None
    if chat.stage == 'awaiting_confirmation' and not (changed or intent or asked):
        return answer, None
    chat.stage = 'awaiting_confirmation'
    preview = build_preview(db, chat)
    return _preview_summary(db, preview), preview


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
    with SessionLocal() as db:
        chat = _client_session(db, session_id, client_id, token)
        if chat.message_version != expected_message_version:
            discard_pending_message(db, chat.id, user_message_id)
            raise HTTPException(409, error_detail('conflict'))
        try:
            advance_message_version(db, chat)
        except HTTPException:
            discard_pending_message(db, session_id, user_message_id)
            raise
        # Records shown to the client are the server bookkeeping, not request data.
        changed = client_state(updated) != client_state(original)
        if chat.stage == 'submitted' and (changed or intent):
            # A sent request is immutable from chat; do not silently change its
            # state or create a second request from a correction.
            updated, intent, changed = original, False, False
            answer = booking_text(original)['already_submitted']
        if updated != original:
            chat.state = updated
        if changed:
            chat.revision += 1
        answer, preview_event = _booking_step(db, chat, answer, changed, intent)
        if not answer.strip():
            raise HTTPException(502, error_detail('service_unavailable'))
        db.add(
            ChatMessage(
                session_id=chat.id,
                role='assistant',
                content=answer,
                reply_to_message_id=user_message_id,
            )
        )
        db.commit()
        return {
            'answer': answer,
            'revision': chat.revision,
            'booking_intent': bool(intent),
            'stage': chat.stage,
            'booking_preview': preview_event,
        }, (answer if preview_event else None)


def _checked_reply(answer, updated, intent):
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
    return answer, updated, intent


def _record_spend(client_id, network, tokens):
    try:
        record_ai_spend(client_id, network, tokens)
    except SQLAlchemyError:
        log.exception('AI token spend was not recorded')


async def _respond_and_save(
    session_id, client_id, token, message, on_chunk=None, image=None, network=None
):
    # Keep each synchronous database phase off the event loop.
    prepared = await _database_call(
        _prepare_message,
        session_id,
        client_id,
        token,
        message,
        on_cancel=partial(_discard_prepared_message, session_id),
    )
    if isinstance(prepared, ServerReply):
        if on_chunk is not None:
            await on_chunk(prepared.result['answer'])
        return prepared.result
    live = on_chunk if isinstance(on_chunk, ReplyStream) else None
    spent = []
    meter = _spent_tokens.set(spent)
    try:
        await asyncio.to_thread(enforce_ai_budget, client_id, network)
        async with ai_capacity(f'client:{client_id}', f'ip:{network}' if network else None):
            photo = {'image': image} if image is not None else {}
            answer, updated, intent = _checked_reply(
                *await respond(message, prepared.state, prepared.history, on_chunk=live, **photo)
            )
        result, summary = await _database_call(
            _save_message_response,
            session_id,
            client_id,
            token,
            prepared.message_version,
            prepared.message_id,
            answer,
            updated,
            prepared.state,
            intent,
        )
    except (Exception, asyncio.CancelledError):
        await _database_call(_discard_failed_message, session_id, prepared.message_id)
        raise
    finally:
        _spent_tokens.reset(meter)
        if spent:
            # A failed or cancelled reply has cost tokens too.
            await _database_call(_record_spend, client_id, network, sum(spent))
    if live is not None:
        await live.finish(summary or result['answer'])
    elif on_chunk is not None:
        await on_chunk(summary or result['answer'])
    return result


def _contact_problems(state):
    """Missing-field codes for the contact data; email and phone are normalized in place."""
    missing = []
    name = state.get('client_name')
    try:
        state['email'] = optional_email(state.get('email'))
    except ValueError:
        missing.append('valid_email')
    if not isinstance(name, str) or not name.strip() or len(name) > 255:
        missing.append('client_name')
    try:
        state['phone'] = normalize_phone(state.get('phone'))
    except ValueError:
        missing.append('phone')
    return missing


def _trip_problems(state):
    missing = []
    duration = state.get('duration_days')
    try:
        validate_travelers_count(state.get('people_count'))
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
    return missing


def build_preview(db, chat):
    state = client_state(chat.state)
    services, unavailable = selected_services(db, state)
    state['selected_services'] = services
    tour = None
    if state.get('tour_id') and 'valid_tour' not in unavailable:
        tour = db.get(Tour, state['tour_id'])
        if tour is not None and not tour.is_active:
            tour = None
    if tour is not None and tour.duration_days:
        # The length of a ready tour is its own property, not the client's wish.
        state['duration_days'] = tour.duration_days
    missing = [*unavailable, *_contact_problems(state), *_trip_problems(state)]
    if tour is not None and 'people_count' not in missing:
        try:
            validate_travelers_count(state.get('people_count'), tour)
        except ValueError:
            missing.append('people_count')
    return {
        'status': 'draft',
        'session_id': chat.id,
        'revision': chat.revision,
        'data': state,
        'missing_fields': missing,
        'complete': not missing,
        'can_confirm': not missing and chat.stage == 'awaiting_confirmation',
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


def _submitted_link(db, chat, revision):
    return (
        db.query(ChatBookingLink)
        .filter(ChatBookingLink.session_id == chat.id, ChatBookingLink.revision == revision)
        .first()
    )


def _open_selection(db, chat):
    """The linked selection, locked; a finished or cancelled one cannot be submitted."""
    selection = (
        db.query(TravelSelection)
        .filter(TravelSelection.session_id == chat.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if selection and processing_status(selection, linked_request(db, selection)) in (
        'cancelled',
        'completed',
    ):
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict')) from None
    return selection


def _travel_request(db, chat, client_id, st):
    tour_note = ''
    destination = st.get('destination')

    if st.get('tour_id'):
        tour = db.get(Tour, st['tour_id'])
        tour_note = f'Тур #{tour.id}: {tour.title}. '
        destination = tour.title

    notes = (
        f'Chat Client: KG-{client_id:06d}; session: {chat.id}. '
        + tour_note
        + f'Язык общения: {st.get("language") or "не указан"}. '
        + f'Бюджет: {st.get("budget") or "не указан"}. '
        + f'Пожелания: {st.get("notes") or "нет"}.'
    )

    if st['selected_services']:
        notes += '\nSelected services: ' + '; '.join(
            f'{item["kind"]} #{item["id"]}: {item["name"]}' for item in st['selected_services']
        )

    return TravelRequest(
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


def confirm_booking(db, chat, client_id, revision, confirmed, *, message=None):
    if not confirmed:
        raise HTTPException(400, error_detail('invalid_request'))

    existing = _submitted_link(db, chat, revision)
    if existing:
        return already_submitted(existing.request_id, client_id)

    if chat.stage != 'awaiting_confirmation':
        raise HTTPException(409, error_detail('conflict'))

    preview = build_preview(db, chat)

    if revision != chat.revision:
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict')) from None
    if preview['missing_fields']:
        return recover_confirmation(db, chat, message)

    selection = _open_selection(db, chat)
    try:
        advance_message_version(db, chat)
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        existing = _submitted_link(db, chat, revision)
        if existing:
            return already_submitted(existing.request_id, client_id)
        record_booking_conflict()
        raise

    obj = _travel_request(db, chat, client_id, preview['data'])
    try:
        db.add(obj)
        db.flush()

        request_id = obj.id

        db.add(
            ChatBookingLink(
                client_id=client_id,
                session_id=chat.id,
                request_id=request_id,
                revision=chat.revision,
            )
        )

        chat.stage = 'submitted'

        if selection:
            selection.status = 'in_progress'
        db.commit()
        publish_new_request(obj.id)
    except IntegrityError:
        db.rollback()
        existing = _submitted_link(db, chat, revision)
        if existing:
            return already_submitted(existing.request_id, client_id)
        record_booking_conflict()
        raise HTTPException(409, error_detail('conflict')) from None
    return {'status': 'submitted', 'request_id': obj.id, 'client_code': f'KG-{client_id:06d}'}


def _confirm_booking_for_client(session_id, client_id, token, revision, confirmed):
    with SessionLocal() as db:
        session = _client_session(db, session_id, client_id, token)
        return confirm_booking(db, session, client_id, revision, confirmed)


async def confirm_booking_serialized(session_id, client_id, token, revision, confirmed):
    async with session_lock(session_id):
        return await _database_call(
            _confirm_booking_for_client, session_id, client_id, token, revision, confirmed
        )


def _remove_service(session_id, client_id, token, kind):
    with SessionLocal() as db:
        session = _client_session(db, session_id, client_id, token)
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
