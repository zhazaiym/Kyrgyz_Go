import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage

import ML.agent as agent
from ML.prompts import PHOTO_PROMPT


def sent_messages(monkeypatch, image=None):
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [])
    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=AsyncMock(return_value={})))
    seen = []

    async def fake_stream(messages):
        seen.append(list(messages))
        yield AIMessageChunk(content='На фото горное озеро.')

    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=fake_stream))
    answer, _, _ = asyncio.run(
        agent._respond(message='Хочу сюда\n[фото]', state={}, history=[], image=image)
    )
    assert answer == 'На фото горное озеро.'
    return seen[0]


def test_photo_is_sent_inline_with_its_message(monkeypatch):
    messages = sent_messages(monkeypatch, image=b'webp-bytes')

    assert isinstance(messages[-2], SystemMessage)
    assert messages[-2].content == PHOTO_PROMPT
    last = messages[-1]
    assert isinstance(last, HumanMessage)
    assert last.content == [
        {'type': 'text', 'text': 'Хочу сюда\n[фото]'},
        {
            'type': 'image',
            'base64': base64.b64encode(b'webp-bytes').decode('ascii'),
            'mime_type': 'image/webp',
        },
    ]


def test_text_message_has_no_photo_instructions(monkeypatch):
    messages = sent_messages(monkeypatch)

    assert messages[-1].content == 'Хочу сюда\n[фото]'
    assert all(message.content != PHOTO_PROMPT for message in messages)
