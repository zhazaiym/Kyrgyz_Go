"""LangChain tool-calling agent; no booking writes are exposed to the LLM."""
import asyncio
import json
import logging
import os
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from mysite.chain.prompts import SYSTEM_PROMPT, EXTRACT_PROMPT
from mysite.chain.tools import READ_TOOLS, list_active_tours

load_dotenv()
for _proxy_key in list(os.environ):
    if _proxy_key.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
        os.environ.pop(_proxy_key, None)
log = logging.getLogger(__name__)
FIELDS = ('client_name', 'phone', 'email', 'tour_id', 'destination', 'travel_date',
          'duration_days', 'people_count', 'budget', 'notes')
CONFIRMATION_TEXT = 'РїРѕРґС‚РІРµСЂР¶РґР°СЋ Р·Р°СЏРІРєСѓ'


def confirmation_allowed(stage: str, message: str) -> bool:
    normalized = ' '.join(message.casefold().strip().rstrip('.! ').split())
    return stage == 'awaiting_confirmation' and normalized == CONFIRMATION_TEXT

class Changes(BaseModel):
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

model_name = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
thinking_level = os.getenv('GEMINI_THINKING_LEVEL', 'LOW').upper()
max_retries = int(os.getenv('GEMINI_MAX_RETRIES', '1'))
model_options = {
    'thinking_config': {'thinking_level': thinking_level},
    'max_retries': max_retries,
    'timeout': 120,
}
llm = ChatGoogleGenerativeAI(
    model=model_name, **model_options
)
extract_model_name = os.getenv('GEMINI_EXTRACT_MODEL', model_name)
extract_llm = ChatGoogleGenerativeAI(
    model=extract_model_name, **model_options
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


async def respond(message: str, state: dict, history: list, on_chunk=None):
    """Return answer, updated state, explicit booking intent. Tools read DB on demand."""
    current = dict(state or {})
    # Read active IDs from company database for safe structured extraction.
    tours = await asyncio.to_thread(list_active_tours.invoke, {})
    ids = [t['id'] for t in tours]
    intent = False
    try:
        changes = await asyncio.wait_for(extractor.ainvoke(EXTRACT_PROMPT.format(
            state=json.dumps(current, ensure_ascii=False), tour_ids=json.dumps(ids),
            message=message)), timeout=45)
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
    for item in history[-24:]:
        if item.role == 'user':
            msgs.append(HumanMessage(content=item.content))
        elif item.role == 'assistant':
            msgs.append(AIMessage(content=item.content))
    msgs.append(HumanMessage(content=message))
    visible_parts = []
    for _ in range(5):
        async def stream_reply():
            complete = None
            async for chunk in agent_llm.astream(msgs):
                complete = chunk if complete is None else complete + chunk
                text = stream_text(chunk.content)
                if text:
                    visible_parts.append(text)
                    if on_chunk is not None:
                        await on_chunk(text)
            if complete is None:
                raise ValueError('Gemini returned empty stream')
            return complete

        reply = await asyncio.wait_for(stream_reply(), timeout=60)
        msgs.append(reply)
        calls = getattr(reply, 'tool_calls', []) or []
        if not calls:
            answer = ''.join(visible_parts).strip()
            if not answer:
                raise ValueError('Gemini returned empty final response')
            return answer, current, intent
        for call in calls:
            name = call.get('name', '')
            tool = tool_map.get(name)
            try:
                result = await asyncio.to_thread(tool.invoke, call.get('args', {})) if tool else {'error': 'Unknown tool'}
            except Exception:
                log.exception('Read-only tool failed: %s', name)
                result = {'error': 'Р”Р°РЅРЅС‹Рµ РєРѕРјРїР°РЅРёРё СЃРµР№С‡Р°СЃ РЅРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕРІРµСЂРёС‚СЊ'}
            msgs.append(ToolMessage(content=json.dumps(result, ensure_ascii=False, default=str),
                                    tool_call_id=call['id'], name=name))
    raise RuntimeError('Agent exceeded maximum tool rounds')

