"""Bounded read-only consultation; booking writes belong to the backend."""

import asyncio
import base64
import json
import logging
import time
from contextvars import ContextVar

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ML.config import integer_setting, output_budget
from ML.context import extraction_context, recent_messages
from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from ML.prompts import EXTRACT_PROMPT, PHOTO_PROMPT, SYSTEM_PROMPT
from ML.provider import LazyClient
from ML.schemas import Changes
from ML.tools import READ_TOOLS, _not_demo
from mysite.api.booking_intent import confirmation_allowed, rejection_allowed
from mysite.api.observability import record_ai_call
from mysite.dates import bishkek_today

__all__ = ['respond', 'output_budget', 'confirmation_allowed', 'rejection_allowed']

log = logging.getLogger(__name__)
FIELDS = (
    'client_name',
    'phone',
    'email',
    'tour_id',
    'destination',
    'travel_date',
    'duration_days',
    'people_count',
    'budget',
    'notes',
    'language',
)

CHAT_IMAGE_MIME_TYPE = 'image/webp'  # mysite/api/chat_images.py re-encodes every photo to WEBP
llm = LazyClient('llm')
extract_llm = LazyClient('extract_llm')
extractor = LazyClient('extractor')
agent_llm = LazyClient('agent_llm')
tool_map = {t.name: t for t in READ_TOOLS}
_timings = ContextVar('ai_response_timings', default=None)


def _record_timing(operation, outcome, duration):
    record_ai_call(operation, outcome, duration)
    timings = _timings.get()
    if timings is not None:
        timings.append((operation, outcome, round(duration, 3)))
    else:
        log.info('AI operation=%s outcome=%s duration_seconds=%.3f', operation, outcome, duration)


async def _measured_call(operation, invoke, *, timeout):
    started = time.perf_counter()
    outcome = 'success'
    try:
        return await asyncio.wait_for(invoke(), timeout=timeout)
    except BaseException as exc:
        if isinstance(exc, TimeoutError):
            outcome = 'timeout'
        elif isinstance(exc, AIError) and exc.code == 'ai_blocked':
            outcome = 'blocked'
        else:
            outcome = 'failure'
        raise
    finally:
        duration = time.perf_counter() - started
        _record_timing(operation, outcome, duration)


def SessionLocal():
    from mysite.database.db import SessionLocal as sessions

    return sessions()


def to_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return ' '.join(
            x if isinstance(x, str) else x.get('text', '')
            for x in content
            if isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get('text'), str))
        ).strip()
    return ''


def stream_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(
            item if isinstance(item, str) else item.get('text', '')
            for item in content
            if isinstance(item, str)
            or (isinstance(item, dict) and isinstance(item.get('text'), str))
        )
    return ''


def active_tour_ids():
    from mysite.database.models import Tour

    with SessionLocal() as db:
        return [
            row[0]
            for row in db.query(Tour.id)
            .filter(Tour.is_active.is_(True), _not_demo(Tour.title))
            .order_by(Tour.id)
            .limit(256)
            .all()
        ]


def user_message(message, image=None):
    """Client turn for Gemini; a photo travels inline with this message only."""
    if image is None:
        return HumanMessage(content=message)
    return HumanMessage(
        content=[
            {'type': 'text', 'text': message},
            {
                'type': 'image',
                'base64': base64.b64encode(image).decode('ascii'),
                'mime_type': CHAT_IMAGE_MIME_TYPE,
            },
        ]
    )


async def _respond(message: str, state: dict, history: list, on_chunk=None, image=None):
    """Extract preferences and consult with bounded read-only tool calls."""
    current = dict(state or {})
    today = bishkek_today().isoformat()
    intent = False
    try:
        ids = await asyncio.to_thread(active_tour_ids)
        selected_id = current.get('tour_id')
        if type(selected_id) is int and selected_id > 0 and selected_id not in ids:
            if await asyncio.to_thread(valid_selected_tour, selected_id):
                ids.append(selected_id)
        changes = await _measured_call(
            'extractor',
            lambda: extractor.ainvoke(
                EXTRACT_PROMPT.format(
                    state=json.dumps(current, ensure_ascii=False),
                    tour_ids=json.dumps(ids),
                    message=message,
                    context=extraction_context(history),
                    today=today,
                )
            ),
            timeout=45,
        )
        if isinstance(changes, dict):
            changes = Changes.model_validate(changes)
        if not isinstance(changes, Changes):
            raise ValueError('Unexpected extractor response')
        for key in changes.clear_fields:
            current.pop(key, None)
        dumped = changes.model_dump(exclude_none=True, exclude={'booking_intent', 'clear_fields'})
        if 'tour_id' in dumped and dumped['tour_id'] not in ids:
            candidate = dumped['tour_id']
            if (
                type(candidate) is int
                and candidate > 0
                and await asyncio.to_thread(valid_selected_tour, candidate)
            ):
                ids.append(candidate)
            else:
                dumped.pop('tour_id')
        if 'destination' in dumped and 'tour_id' not in dumped:
            if current.get('tour_id') is not None:
                dumped.pop('destination', None)
        if 'tour_id' in dumped:
            current.pop('destination', None)
        for k, v in dumped.items():
            if k not in FIELDS or v == '':
                continue
            if k == 'tour_id' and v not in ids:
                continue
            current[k] = v
        intent = changes.booking_intent
    except (
        *PROVIDER_ERRORS,
        asyncio.TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ) as exc:
        # Preserve state atomically; never log SDK exception text or user prompts.
        current = dict(state or {})
        intent = False
        failure = classify_error(exc)
        log.warning('Structured extraction failed: %s', failure.code)

    msgs = [
        SystemMessage(
            content=SYSTEM_PROMPT.format(state=json.dumps(current, ensure_ascii=False), today=today)
        )
    ]
    for item in recent_messages(history):
        if item.role == 'user':
            msgs.append(HumanMessage(content=item.content))
        elif item.role == 'assistant':
            msgs.append(AIMessage(content=item.content))
    if image is not None:
        msgs.append(SystemMessage(content=PHOTO_PROMPT))
    msgs.append(user_message(message, image))
    compact_retry = False
    tool_calls_used = 0
    for _ in range(5):
        visible_parts = []

        async def stream_reply():
            complete = None
            payload_bytes = 0
            chunk_count = 0
            visible_characters = 0
            async for chunk in agent_llm.astream(msgs):
                chunk_count += 1
                if chunk_count > 8192:
                    raise AIError('ai_invalid_response', 'Gemini stream exceeded chunk budget')
                try:
                    payload_bytes += len(chunk.model_dump_json(exclude_none=True).encode('utf-8'))
                except (ValueError, TypeError) as exc:
                    raise AIError('ai_invalid_response') from exc
                # Include reasoning, tool arguments and metadata, before merging.
                if payload_bytes > 1_048_576:
                    raise AIError('ai_invalid_response', 'Gemini stream exceeded payload budget')
                complete = chunk if complete is None else complete + chunk
                text = stream_text(chunk.content)
                if text:
                    visible_characters += len(text)
                    visible_parts.append(text)
                    if visible_characters > 65_536:
                        raise AIError('ai_invalid_response')
            if complete is None:
                raise AIError('ai_invalid_response', 'Gemini returned empty stream')
            return complete

        reply = await _measured_call('generation', stream_reply, timeout=60)
        finish_reason = (
            str(reply.response_metadata.get('finish_reason', '')).upper().rsplit('.', 1)[-1]
        )
        if finish_reason in {
            'SAFETY',
            'RECITATION',
            'BLOCKLIST',
            'PROHIBITED_CONTENT',
            'SPII',
            'IMAGE_SAFETY',
        }:
            raise AIError('ai_blocked')
        if getattr(reply, 'invalid_tool_calls', None):
            raise AIError('ai_invalid_response')
        if finish_reason.endswith('MAX_TOKENS') or finish_reason == 'LENGTH':
            if compact_retry:
                raise AIError('ai_invalid_response', 'Gemini response exceeded output budget')
            compact_retry = True
            msgs.append(
                SystemMessage(
                    content=(
                        'Переформулируй ответ на языке клиента заметно компактнее, но законченным. '
                        'Сохрани главное предложение, существенные условия и нужный вопрос. '
                        'Используй только проверенные факты, не повторяй вступление. '
                        'Если вся программа не помещается, предложи продолжить её отдельно.'
                    )
                )
            )
            continue
        if finish_reason not in {'', 'STOP'}:
            raise AIError('ai_invalid_response')
        msgs.append(reply)
        calls = getattr(reply, 'tool_calls', []) or []
        if not calls:
            answer = ''.join(visible_parts).strip()
            if not answer:
                raise AIError('ai_invalid_response', 'Gemini returned empty final response')
            if on_chunk is not None:
                for text in visible_parts:
                    await on_chunk(text)
            return answer, current, intent
        tool_calls_used += len(calls)
        if tool_calls_used > 8:
            raise AIError('ai_invalid_response', 'Agent exceeded tool call budget')
        call_ids = [call.get('id') for call in calls]
        if any(not isinstance(value, str) or not value for value in call_ids) or len(
            set(call_ids)
        ) != len(call_ids):
            raise AIError('ai_invalid_response')
        for call in calls:
            if not isinstance(call.get('args'), dict):
                raise AIError('ai_invalid_response')
            name = call.get('name', '')
            tool = tool_map.get(name)
            tool_start = time.perf_counter()
            tool_outcome = 'success' if tool else 'failure'
            try:
                result = (
                    await asyncio.wait_for(
                        asyncio.to_thread(tool.invoke, call.get('args', {})), timeout=15
                    )
                    if tool
                    else {'error': 'Unknown tool'}
                )
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, TimeoutError) as exc:
                tool_outcome = 'timeout' if isinstance(exc, TimeoutError) else 'failure'
                log.warning('Read-only tool failed: %s', type(exc).__name__)
                result = {'error': 'Данные компании сейчас не удалось проверить'}
            finally:
                tool_seconds = time.perf_counter() - tool_start
                _record_timing('tool', tool_outcome, tool_seconds)
            encoded = json.dumps(result, ensure_ascii=False, default=str)
            if len(encoded) > 16_000:
                encoded = json.dumps(
                    {'error': 'Результат слишком большой. Уточните запрос; выдача неполная.'},
                    ensure_ascii=False,
                )
            msgs.append(ToolMessage(content=encoded, tool_call_id=call['id'], name=name))
    raise AIError('ai_invalid_response', 'Agent exceeded maximum tool rounds')


def valid_selected_tour(identity):
    from mysite.database.models import Tour

    with SessionLocal() as db:
        return (
            db.query(Tour.id)
            .filter(Tour.id == identity, Tour.is_active.is_(True), _not_demo(Tour.title))
            .first()
            is not None
        )


async def respond(message: str, state: dict, history: list, on_chunk=None, image=None):
    started = time.perf_counter()
    timings = []
    timing_token = _timings.set(timings)
    outcome = 'failure'
    try:
        async with asyncio.timeout(integer_setting('CHAT_RESPONSE_TIMEOUT', 150, 10, 170)):
            result = await _respond(message, state, history, on_chunk, image)
            outcome = 'success'
            return result
    except AIError as exc:
        outcome = 'timeout' if exc.code == 'ai_timeout' else 'failure'
        raise
    except (*PROVIDER_ERRORS, TimeoutError) as exc:
        failure = classify_error(exc)
        outcome = 'timeout' if failure.code == 'ai_timeout' else 'failure'
        log.warning('Gemini consultation failed: %s', failure.code)
        raise failure from None
    finally:
        _timings.reset(timing_token)
        log.info(
            'AI response outcome=%s duration_seconds=%.3f phases=%s',
            outcome,
            time.perf_counter() - started,
            timings,
        )
