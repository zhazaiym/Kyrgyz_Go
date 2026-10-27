"""LangChain tool-calling agent; no booking writes are exposed to the LLM."""
import asyncio
import json
import logging
import os
import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from mysite.chain.prompts import SYSTEM_PROMPT, EXTRACT_PROMPT
from mysite.chain.tools import READ_TOOLS, _not_demo
from mysite.database.db import SessionLocal
from mysite.database.models import Tour

load_dotenv()
for _proxy_key in list(os.environ):
    if _proxy_key.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
        os.environ.pop(_proxy_key, None)
log = logging.getLogger(__name__)
FIELDS = ('client_name', 'phone', 'email', 'tour_id', 'destination', 'travel_date',
          'duration_days', 'people_count', 'budget', 'notes', 'language')
CONFIRMATION_TEXT = 'подтверждаю заявку'
CONFIRMATION_REPLIES = {
    'да подтверждаю', 'подтверждаю', CONFIRMATION_TEXT,
    'я готова бронировать тур', 'я готов бронировать тур',
    'я готова бронировать туры', 'я готов бронировать туры',
    'я готова забронировать тур', 'я готов забронировать тур',
    'yes confirm', 'i confirm', 'confirm', 'confirm request',
    'ооба ырастайм', 'ырастайм', 'өтүнмөнү ырастайм',
    'ich bestätige', 'ich bestätige die anfrage', '确认提交', '确认申请',
}
REJECTION_REPLIES = {
    'нет', 'не подтверждаю', 'не отправляй', 'отмена',
    'нет спасибо', 'не отправляйте', 'не отправляйте заявку', 'пока не отправляй', 'пока не отправляйте',
    'не оформляй', 'не оформляйте', 'не хочу бронировать',
    'я передумал', 'я передумала', 'я передумал бронировать', 'я передумала бронировать',
    'no', 'no thanks', 'not now', 'do not submit', 'do not send yet',
    'don t send yet', 'cancel', 'cancel request',
    'жок', 'жок рахмат', 'ырастабайм', 'жөнөтпө', 'азыр жөнөтпө',
    'nein', 'nicht absenden', '不发送', '取消',
}


def normalized_reply(message: str) -> str:
    return ' '.join(re.sub(r'[^\w\s]', ' ', message.casefold()).split())


def confirmation_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and normalized_reply(message) in CONFIRMATION_REPLIES


def rejection_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and normalized_reply(message) in REJECTION_REPLIES

class Changes(BaseModel):
    language: Literal['ru', 'ky', 'en', 'de', 'zh'] | None = None
    client_name: str | None = None
    phone: str | None = None
    email: str | None = None
    tour_id: int | None = None
    destination: str | None = None
    travel_date: str | None = Field(default=None, description='Unambiguous YYYY-MM-DD')
    duration_days: int | None = Field(default=None, ge=1)
    people_count: int | None = Field(default=None, ge=1)
    budget: str | None = None
    notes: str | None = None
    clear_fields: list[Literal[
        'client_name', 'phone', 'email', 'tour_id', 'destination',
        'travel_date', 'duration_days', 'people_count', 'budget', 'notes'
    ]] = Field(default_factory=list)
    booking_intent: bool = False


def output_budget(name: str, default: int, maximum: int) -> int:
    return max(256, min(maximum, int(os.getenv(name, str(default)))))

model_name = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
thinking_level = os.getenv('GEMINI_THINKING_LEVEL', 'LOW').upper()
max_retries = int(os.getenv('GEMINI_MAX_RETRIES', '1'))
model_options = {
    'thinking_config': {'thinking_level': thinking_level},
    'max_retries': max_retries,
    'timeout': 120,
}
llm = ChatGoogleGenerativeAI(
    model=model_name, max_output_tokens=output_budget('CHAT_MAX_OUTPUT_TOKENS', 1536, 4096),
    **model_options
)
extract_model_name = os.getenv('GEMINI_EXTRACT_MODEL', model_name)
extract_llm = ChatGoogleGenerativeAI(
    model=extract_model_name,
    max_output_tokens=output_budget('CHAT_EXTRACT_MAX_OUTPUT_TOKENS', 512, 1024),
    **model_options
)
extractor = extract_llm.with_structured_output(Changes, method='json_schema')
agent_llm = llm.bind_tools(READ_TOOLS)
tool_map = {t.name: t for t in READ_TOOLS}


def to_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return ' '.join(x if isinstance(x, str) else x.get('text', '')
                        for x in content if isinstance(x, str) or (isinstance(x, dict) and isinstance(x.get('text'), str))).strip()
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
    with SessionLocal() as db:
        return [row[0] for row in db.query(Tour.id).filter(
            Tour.is_active.is_(True), _not_demo(Tour.title)
        ).all()]


def recent_messages(history):
    message_limit = max(1, int(os.getenv('CHAT_HISTORY_MESSAGES', '12')))
    character_limit = max(1, int(os.getenv('CHAT_HISTORY_CHARACTERS', '8000')))
    selected = []
    characters = 0
    for item in reversed(history[-message_limit:]):
        if item.role not in ('user', 'assistant') or not isinstance(item.content, str):
            continue
        if characters + len(item.content) > character_limit:
            break
        selected.append(item)
        characters += len(item.content)
    return list(reversed(selected))


def extraction_context(history):
    remaining = 2400
    selected = []
    for item in reversed(history[-4:]):
        if item.role not in ('user', 'assistant') or not isinstance(item.content, str):
            continue
        content = item.content[-remaining:]
        selected.append({'role': item.role, 'content': content})
        remaining -= len(content)
        if remaining <= 0:
            break
    return json.dumps(list(reversed(selected)), ensure_ascii=False)


async def respond(message: str, state: dict, history: list, on_chunk=None):
    """Return answer, updated state, explicit booking intent. Tools read DB on demand."""
    current = dict(state or {})
    intent = False
    try:
        ids = await asyncio.to_thread(active_tour_ids)
        changes = await asyncio.wait_for(extractor.ainvoke(EXTRACT_PROMPT.format(
            state=json.dumps(current, ensure_ascii=False), tour_ids=json.dumps(ids),
            message=message, context=extraction_context(history))), timeout=45)
        if isinstance(changes, dict):
            changes = Changes.model_validate(changes)
        if not isinstance(changes, Changes):
            raise ValueError('Unexpected extractor response')
        for key in changes.clear_fields:
            current.pop(key, None)
        dumped = changes.model_dump(
            exclude_none=True, exclude={'booking_intent', 'clear_fields'}
        )
        if 'tour_id' in dumped and dumped['tour_id'] not in ids:
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
    except Exception:
        # Conversation remains usable; never modify booking state after failed extraction.
        log.exception('Structured extraction failed; continuing without state changes')

    msgs = [SystemMessage(content=SYSTEM_PROMPT.format(
        state=json.dumps(current, ensure_ascii=False), today=date.today().isoformat()))]
    for item in recent_messages(history):
        if item.role == 'user':
            msgs.append(HumanMessage(content=item.content))
        elif item.role == 'assistant':
            msgs.append(AIMessage(content=item.content))
    msgs.append(HumanMessage(content=message))
    compact_retry = False
    for _ in range(5):
        visible_parts = []
        async def stream_reply():
            complete = None
            async for chunk in agent_llm.astream(msgs):
                complete = chunk if complete is None else complete + chunk
                text = stream_text(chunk.content)
                if text:
                    visible_parts.append(text)
            if complete is None:
                raise ValueError('Gemini returned empty stream')
            return complete

        reply = await asyncio.wait_for(stream_reply(), timeout=60)
        finish_reason = str(reply.response_metadata.get('finish_reason', '')).upper()
        if finish_reason.endswith('MAX_TOKENS') or finish_reason == 'LENGTH':
            if compact_retry:
                raise RuntimeError('Gemini response exceeded output budget')
            compact_retry = True
            msgs.append(SystemMessage(content=(
                'Переформулируй ответ на языке клиента заметно компактнее, но законченным. '
                'Сохрани главное предложение, существенные условия и нужный вопрос. '
                'Используй только проверенные факты, не повторяй вступление. '
                'Если вся программа не помещается, предложи продолжить её отдельно.'
            )))
            continue
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
        for call in calls:
            name = call.get('name', '')
            tool = tool_map.get(name)
            try:
                result = await asyncio.to_thread(tool.invoke, call.get('args', {})) if tool else {'error': 'Unknown tool'}
            except Exception:
                log.exception('Read-only tool failed: %s', name)
                result = {'error': 'Данные компании сейчас не удалось проверить'}
            msgs.append(ToolMessage(content=json.dumps(result, ensure_ascii=False, default=str),
                                    tool_call_id=call['id'], name=name))
    raise RuntimeError('Agent exceeded maximum tool rounds')

