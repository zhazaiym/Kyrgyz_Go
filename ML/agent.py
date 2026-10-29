"""Bounded read-only consultation; booking writes belong to the backend."""

import asyncio
import json
import logging
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ML.config import integer_setting, output_budget
from ML.context import extraction_context, recent_messages
from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from ML.prompts import EXTRACT_PROMPT, SYSTEM_PROMPT
from ML.provider import LazyClient
from ML.schemas import Changes
from ML.tools import READ_TOOLS, _not_demo
from mysite.api.booking_intent import confirmation_allowed, rejection_allowed

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

llm = LazyClient('llm')
extract_llm = LazyClient('extract_llm')
extractor = LazyClient('extractor')
agent_llm = LazyClient('agent_llm')
tool_map = {t.name: t for t in READ_TOOLS}


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


async def _respond(message: str, state: dict, history: list, on_chunk=None):
    """Return answer, updated state, explicit booking intent. Tools read DB on demand."""
    current = dict(state or {})
    intent = False
    try:
        ids = await asyncio.to_thread(active_tour_ids)
        selected_id = current.get('tour_id')
        if type(selected_id) is int and selected_id > 0 and selected_id not in ids:
            if await asyncio.to_thread(valid_selected_tour, selected_id):
                ids.append(selected_id)
        changes = await asyncio.wait_for(
            extractor.ainvoke(
                EXTRACT_PROMPT.format(
                    state=json.dumps(current, ensure_ascii=False),
                    tour_ids=json.dumps(ids),
                    message=message,
                    context=extraction_context(history),
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
            current.pop('tour_id', None)
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
            content=SYSTEM_PROMPT.format(
                state=json.dumps(current, ensure_ascii=False), today=date.today().isoformat()
            )
        )
    ]
    for item in recent_messages(history):
        if item.role == 'user':
            msgs.append(HumanMessage(content=item.content))
        elif item.role == 'assistant':
            msgs.append(AIMessage(content=item.content))
    msgs.append(HumanMessage(content=message))
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
                raise ValueError('Gemini returned empty stream')
            return complete

        reply = await asyncio.wait_for(stream_reply(), timeout=60)
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
                raise ValueError('Gemini returned empty final response')
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
            try:
                result = (
                    await asyncio.wait_for(
                        asyncio.to_thread(tool.invoke, call.get('args', {})), timeout=15
                    )
                    if tool
                    else {'error': 'Unknown tool'}
                )
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, TimeoutError) as exc:
                log.warning('Read-only tool failed: %s', type(exc).__name__)
                result = {'error': 'Данные компании сейчас не удалось проверить'}
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


async def respond(message: str, state: dict, history: list, on_chunk=None):
    try:
        async with asyncio.timeout(integer_setting('CHAT_RESPONSE_TIMEOUT', 150, 10, 170)):
            return await _respond(message, state, history, on_chunk)
    except AIError:
        raise
    except (*PROVIDER_ERRORS, TimeoutError) as exc:
        failure = classify_error(exc)
        log.warning('Gemini consultation failed: %s', failure.code)
        raise failure from None
