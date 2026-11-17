"""Bounded read-only consultation; booking writes belong to the backend."""

import asyncio
import base64
import json
import logging
import re
import time
from contextvars import ContextVar
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ML.config import chat_setting
from ML.context import extraction_context, recent_messages, text_content
from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from ML.grounding import destination_is_trusted
from ML.price_grounding import PRICE_RECHECK, PriceEvidence
from ML.prompts import CONSULT_DATA, EXTRACT_DATA, EXTRACT_PROMPT, PHOTO_PROMPT, SYSTEM_PROMPT
from ML.provider import LazyClient
from ML.runtime import app
from ML.schemas import Changes
from ML.tools import CATALOGUE_KINDS, READ_TOOLS, active_tour_ids, valid_selected_tour

__all__ = ['respond']

log = logging.getLogger(__name__)

CHAT_IMAGE_MIME_TYPE = 'image/webp'  # mysite/api/chat_images.py re-encodes every photo to WEBP
# State key kept by the server, not taken from the client's words: catalogue
# records the client has been shown, newest reply first. A tour is chosen only from it.
SHOWN = '_shown'
SHOWN_LIMIT = 12
# A ready tour has its own place and length: earlier wishes for them lose meaning.
TOUR_OWNED_FIELDS = ('destination', 'duration_days')
BLOCKED_FINISH_REASONS = {
    'SAFETY',
    'RECITATION',
    'BLOCKLIST',
    'PROHIBITED_CONTENT',
    'SPII',
    'IMAGE_SAFETY',
}
COMPACT_RETRY_PROMPT = (
    'Переформулируй ответ на языке клиента заметно компактнее, но законченным. '
    'Сохрани главное предложение, существенные условия и нужный вопрос. '
    'Используй только проверенные факты, не повторяй вступление. '
    'Если вся программа не помещается, предложи продолжить её отдельно.'
)
extractor = LazyClient('extractor')
agent_llm = LazyClient('agent_llm')
tool_map = {t.name: t for t in READ_TOOLS}
_timings = ContextVar('ai_response_timings', default=None)


# A labelled record or client number: "ID 12", "(id: 12)", "айди №12", "#12", "KG-000012".
_ID_LABEL = r'(?<!\w)(?:id|ид|айди)(?!\w)[ \t]*[:=#№-]?[ \t]*'
_ID_MENTION = re.compile(
    r'[ \t]*[(\[]?(?:\bKG-\d+|' + _ID_LABEL + r'\d+|#[ \t]?\d+)[)\]]?', re.IGNORECASE
)
# The end of a piece that the next piece may turn into a mention.
_ID_UNFINISHED = re.compile(
    r'[ \t]*(?:[(\[]|[(\[]?(?:\bKG?-?\d*|(?<!\w)(?:i|и|а|ай|айд)|'
    + _ID_LABEL
    + r'\d*|#[ \t]?\d*))$',
    re.IGNORECASE,
)


class IdScrubber:
    """Drops record and client IDs from reply text while it is streamed.

    The prompt already forbids them; this makes it certain. Text that may be
    the start of a mention waits for the next piece before it is shown.
    """

    def __init__(self):
        self.pending = ''

    def feed(self, text):
        self.pending += text
        unfinished = _ID_UNFINISHED.search(self.pending)
        safe = unfinished.start() if unfinished else len(self.pending)
        ready, self.pending = self.pending[:safe], self.pending[safe:]
        return _ID_MENTION.sub('', ready)

    def flush(self):
        ready, self.pending = self.pending, ''
        return _ID_MENTION.sub('', ready)


def _record_timing(operation, outcome, duration):
    app.record_ai_call(operation, outcome, duration)
    timings = _timings.get()
    if timings is not None:
        timings.append((operation, outcome, round(duration, 3)))
    else:
        log.info('AI operation=%s outcome=%s duration_seconds=%.3f', operation, outcome, duration)


def _record_tokens(operation, reply):
    """Report what a model call cost; the application keeps the budget."""
    usage = getattr(reply, 'usage_metadata', None)
    tokens = usage.get('total_tokens') if isinstance(usage, dict) else None
    if type(tokens) is int and tokens > 0:
        app.record_ai_tokens(operation, tokens)


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


REQUIRED_FOR_REQUEST = (
    ('tour_or_destination', 'тур или направление'),
    ('travel_date', 'точная дата начала поездки'),
    ('people_count', 'общее число людей'),
    ('client_name', 'имя'),
    ('phone', 'телефон'),
)


def missing_for_request(state):
    """Required request fields the client has not given yet, for the agent to ask."""
    present = {
        'tour_or_destination': state.get('tour_id') or state.get('destination'),
        'travel_date': state.get('travel_date'),
        'people_count': state.get('people_count'),
        'client_name': state.get('client_name'),
        'phone': state.get('phone'),
    }
    missing = [label for key, label in REQUIRED_FOR_REQUEST if not present[key]]
    travel_date = state.get('travel_date')
    if travel_date:
        try:
            past = date.fromisoformat(travel_date) < app.today()
        except (TypeError, ValueError):
            past = True
        if past:
            missing.append('дата поездки в будущем (прошедшая или неверная не подходит)')
    return missing


def client_state(state):
    """The state without the server's own bookkeeping."""
    return {key: value for key, value in (state or {}).items() if key != SHOWN}


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


def extraction_messages(message, state, history, today):
    """The rules, the server's data and the client's words as three separate messages."""
    data = EXTRACT_DATA.format(
        today=today,
        state=json.dumps(client_state(state), ensure_ascii=False),
        shown=json.dumps(state.get(SHOWN) or [], ensure_ascii=False),
        context=extraction_context(history),
    )
    return [
        SystemMessage(content=EXTRACT_PROMPT),
        HumanMessage(content=data),
        HumanMessage(content=message),
    ]


def _extracted_changes(result):
    if isinstance(result, dict) and 'raw' in result and 'parsed' in result:
        _record_tokens('extractor', result['raw'])
        result = result['parsed']  # None when the reply does not fit the schema
    if isinstance(result, dict):
        result = Changes.model_validate(result)
    if not isinstance(result, Changes):
        raise ValueError('Unexpected extractor response')
    return result


async def _tour_selectable(candidate, state):
    """True for an active tour the client was shown here or has already chosen (on the site).

    The model has no other reliable link between a tour's name and its number,
    so a number from anywhere else is a guess.
    """
    known = {
        item.get('id')
        for item in state.get(SHOWN) or []
        if isinstance(item, dict) and item.get('kind') == 'tour'
    }
    known.add(state.get('tour_id'))
    if type(candidate) is not int or candidate <= 0 or candidate not in known:
        return False
    if candidate in await asyncio.to_thread(active_tour_ids):
        return True
    return await asyncio.to_thread(valid_selected_tour, candidate)


def apply_changes(state, changes, tour_selectable, spoken):
    """The state after the extracted changes; calls no model and no database.

    ``spoken`` is what the client and the assistant wrote: a destination absent
    from it is discarded.
    """
    current = dict(state)
    for key in changes.clear_fields:
        current.pop(key, None)
    dumped = changes.model_dump(exclude_none=True, exclude={'booking_intent', 'clear_fields'})
    if 'tour_id' in dumped and not tour_selectable:
        dumped.pop('tour_id')
    if 'tour_id' in dumped:
        for key in TOUR_OWNED_FIELDS:
            current.pop(key, None)
            dumped.pop(key, None)
    elif current.get('tour_id') is not None:
        dumped.pop('destination', None)
    if 'destination' in dumped:
        language = dumped.get('language') or current.get('language')
        if not destination_is_trusted(dumped['destination'], spoken, language):
            log.warning('Discarded extracted destination absent from the conversation')
            dumped.pop('destination')
    current.update((key, value) for key, value in dumped.items() if value != '')
    return current


def _numbered_tour_choice(message, state, history):
    text = message.strip().casefold()
    match = re.fullmatch(r'(\d{1,2})(?:-?(?:й|ый|ой))?(?:\s+вариант)?[.!]?', text)
    if match is None:
        return None
    if text.rstrip('.!').isdigit():
        last = next((item.content for item in reversed(history) if item.role == 'assistant'), '')
        if not re.search(r'выб|вариант|which|choose|welch|哪个', last, re.IGNORECASE):
            return None
    items = state.get(SHOWN) or []
    index = int(match[1]) - 1
    if not 0 <= index < len(items):
        return None
    item = items[index]
    return item.get('id') if isinstance(item, dict) and item.get('kind') == 'tour' else None


async def _extract(message, state, history, today):
    """State updated from the client's message, and whether they want to book.

    A failed extraction keeps the state exactly as it was and reports no intent.
    """
    current = dict(state or {})
    try:
        choice = _numbered_tour_choice(message, current, history)
        if choice is not None and await _tour_selectable(choice, current):
            # A direct selection is already unambiguous server-owned data;
            # it must not depend on another successful model request.
            return apply_changes(current, Changes(tour_id=choice), True, message), False
        changes = _extracted_changes(
            await _measured_call(
                'extractor',
                lambda: extractor.ainvoke(extraction_messages(message, current, history, today)),
                timeout=45,
            )
        )
        selectable = changes.tour_id is not None and await _tour_selectable(
            changes.tour_id, current
        )
        spoken = message + '\n' + extraction_context(history)
        return apply_changes(current, changes, selectable, spoken), changes.booking_intent
    except (
        *PROVIDER_ERRORS,
        asyncio.TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
    ) as exc:
        # Preserve state atomically; never log SDK exception text or user prompts.
        failure = classify_error(exc)
        log.warning('Structured extraction failed: %s', failure.code)
        return dict(state or {}), False


def shown_items(found, answer, previous):
    """Records of this reply in the order the client reads them, then the earlier ones."""
    text = answer.casefold()
    named = sorted(
        (text.find(title.casefold()), key)
        for key, title in found.items()
        if title.casefold() in text
    )
    # A translated reply names no title literally: keep what the tools returned.
    latest = [key for _, key in named] or list(found)
    items = [{'kind': key[0], 'id': key[1], 'title': found[key]} for key in latest]
    earlier = [
        item
        for item in previous or []
        if isinstance(item, dict) and (item.get('kind'), item.get('id')) not in found
    ]
    return (items + earlier)[:SHOWN_LIMIT]


async def _respond(message: str, state: dict, history: list, on_chunk=None, image=None):
    """Extract preferences and consult with bounded read-only tool calls.

    Extraction runs alongside the consultation, so the client is not kept
    waiting for it before the first words of the reply. The consultant
    therefore sees the state as it was before this message and reads the
    message itself for what it adds; the extracted state is what is returned.

    ``on_chunk`` receives the visible reply text. A listener with an async
    ``reset()`` method gets each piece live, as the model produces it, and is
    reset when that text will not be kept (the round turns into tool calls or a
    compact retry); on an error the caller must reset it. A plain callback gets
    only the final answer, once it is known to be kept.
    """
    today = app.today().isoformat()
    extraction = asyncio.create_task(_extract(message, state, history, today))
    try:
        parts, found = await _consult(message, dict(state or {}), history, on_chunk, image, today)
        current, intent = await extraction
    except BaseException:
        extraction.cancel()
        await asyncio.gather(extraction, return_exceptions=True)
        raise
    if on_chunk is not None and not callable(getattr(on_chunk, 'reset', None)):
        for text in parts:
            await on_chunk(text)
    answer = ''.join(parts).strip()
    if found:
        current[SHOWN] = shown_items(found, answer, current.get(SHOWN))
    return answer, current, intent


def _consult_messages(message, known, history, image, today):
    """Fixed rules first; everything taken from the client's words follows as data."""
    prompt_state = {**client_state(known), 'missing_for_request': missing_for_request(known)}
    msgs = [SystemMessage(content=SYSTEM_PROMPT)]
    for item in recent_messages(history):
        if item.role == 'user':
            msgs.append(HumanMessage(content=item.content))
        elif item.role == 'assistant':
            msgs.append(AIMessage(content=item.content))
    msgs.append(
        HumanMessage(
            content=CONSULT_DATA.format(
                state=json.dumps(prompt_state, ensure_ascii=False), today=today
            )
        )
    )
    if image is not None:
        msgs.append(SystemMessage(content=PHOTO_PROMPT))
    msgs.append(user_message(message, image))
    return msgs


async def _stream_round(msgs, emit):
    """One model round: the merged reply; its visible text goes to ``emit`` as it comes."""
    complete = None
    scrubber = IdScrubber()
    payload_bytes = 0
    chunk_count = 0
    visible_characters = 0
    try:
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
            visible_characters += len(text_content(chunk.content))
            if visible_characters > 65_536:
                raise AIError('ai_invalid_response')
            await emit(scrubber.feed(text_content(chunk.content)))
        await emit(scrubber.flush())
    finally:
        _record_tokens('generation', complete)
    if complete is None:
        raise AIError('ai_invalid_response', 'Gemini returned empty stream')
    return complete


def _reply_truncated(reply):
    """True when the reply hit the output budget; a blocked or broken reply raises."""
    reason = str(reply.response_metadata.get('finish_reason', '')).upper().rsplit('.', 1)[-1]
    if reason in BLOCKED_FINISH_REASONS:
        raise AIError('ai_blocked')
    if getattr(reply, 'invalid_tool_calls', None):
        raise AIError('ai_invalid_response')
    if reason.endswith('MAX_TOKENS') or reason == 'LENGTH':
        return True
    if reason not in {'', 'STOP'}:
        raise AIError('ai_invalid_response')
    return False


def _catalogue_records(result):
    """(kind, id) -> title for each catalogue record in a tool result."""
    rows = result.get('items') if isinstance(result, dict) else None
    return {
        (row['kind'], row['id']): row['title'][:160]
        for row in (rows if isinstance(rows, list) else [result])
        if isinstance(row, dict)
        and row.get('kind') in CATALOGUE_KINDS
        and type(row.get('id')) is int
        and isinstance(row.get('title'), str)
    }


async def _call_tool(call):
    tool = tool_map.get(call.get('name', ''))
    started = time.perf_counter()
    outcome = 'success' if tool else 'failure'
    try:
        if tool is None:
            return {'error': 'Unknown tool'}
        return await asyncio.wait_for(asyncio.to_thread(tool.invoke, call['args']), timeout=15)
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, TimeoutError) as exc:
        outcome = 'timeout' if isinstance(exc, TimeoutError) else 'failure'
        log.warning('Read-only tool failed: %s', type(exc).__name__)
        return {'error': 'Данные компании сейчас не удалось проверить'}
    finally:
        _record_timing('tool', outcome, time.perf_counter() - started)


async def _run_tools(calls, found, prices=None):
    """Tool messages of one round; catalogue records they returned are added to ``found``."""
    call_ids = [call.get('id') for call in calls]
    if any(not isinstance(value, str) or not value for value in call_ids) or len(
        set(call_ids)
    ) != len(call_ids):
        raise AIError('ai_invalid_response')
    messages = []
    for call in calls:
        if not isinstance(call.get('args'), dict):
            raise AIError('ai_invalid_response')
        result = await _call_tool(call)
        encoded = json.dumps(result, ensure_ascii=False, default=str)
        if len(encoded) > 16_000:
            encoded = json.dumps(
                {'error': 'Результат слишком большой. Уточните запрос; выдача неполная.'},
                ensure_ascii=False,
            )
        else:
            found.update(_catalogue_records(result))
            if prices is not None:
                prices.add(result)
        messages.append(
            ToolMessage(content=encoded, tool_call_id=call['id'], name=call.get('name', ''))
        )
    return messages


async def _consult(message, known, history, on_chunk, image, today):
    """Pieces of the reply, written from the state before this message, and the records found."""
    live = callable(getattr(on_chunk, 'reset', None))
    msgs = _consult_messages(message, known, history, image, today)
    found = {}
    prices = PriceEvidence()
    price_retry = False
    compact_retry = False
    tool_calls_used = 0
    # A photo turn may need several searches before reading the matching item.
    for _ in range(7 if image is not None else 5):
        visible_parts = []
        held = []

        async def emit(text, parts=visible_parts):
            if text:
                parts.append(text)
                if live:
                    # A numeric claim waits for validation, including when its
                    # amount and currency arrive in separate stream chunks.
                    if held or re.search(r'\d', text):
                        held.append(text)
                    else:
                        await on_chunk(text)

        reply = await _measured_call('generation', lambda: _stream_round(msgs, emit), timeout=60)
        if _reply_truncated(reply):
            if compact_retry:
                raise AIError('ai_invalid_response', 'Gemini response exceeded output budget')
            compact_retry = True
            if live:
                await on_chunk.reset()
            msgs.append(SystemMessage(content=COMPACT_RETRY_PROMPT))
            continue
        msgs.append(reply)
        calls = getattr(reply, 'tool_calls', []) or []
        if not calls:
            if not ''.join(visible_parts).strip():
                raise AIError('ai_invalid_response', 'Gemini returned empty final response')
            budget_context = str(known.get('budget') or '') + '\n' + message
            if not prices.accepts(''.join(visible_parts), budget_context):
                if live:
                    await on_chunk.reset()
                if price_retry:
                    safe = prices.fallback(known.get('language'))
                    if live:
                        await on_chunk(safe)
                    return [safe], found
                price_retry = True
                msgs.pop()  # the rejected draft must not become conversation history
                msgs.append(SystemMessage(content=PRICE_RECHECK))
                continue
            if live:
                for text in held:
                    await on_chunk(text)
            return visible_parts, found
        if live:
            await on_chunk.reset()  # text before a tool call is a preamble, not the answer
        tool_calls_used += len(calls)
        if tool_calls_used > 8:
            raise AIError('ai_invalid_response', 'Agent exceeded tool call budget')
        msgs += await _run_tools(calls, found, prices)
    raise AIError('ai_invalid_response', 'Agent exceeded maximum tool rounds')


async def respond(message: str, state: dict, history: list, on_chunk=None, image=None):
    started = time.perf_counter()
    timings = []
    timing_token = _timings.set(timings)
    outcome = 'failure'
    try:
        async with asyncio.timeout(chat_setting('CHAT_RESPONSE_TIMEOUT')):
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
