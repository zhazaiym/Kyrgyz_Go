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


def test_photo_prompt_requires_catalogue_search_and_details():
    for required in ('search_catalogue', 'get_catalogue_item', 'скриншот', 'программа'):
        assert required in PHOTO_PROMPT


def test_photo_turn_searches_catalogue_and_describes_found_tour(monkeypatch):
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [])
    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=AsyncMock(return_value={})))
    replies = iter(
        [
            AIMessageChunk(
                content='',
                tool_calls=[
                    {
                        'name': 'search_catalogue',
                        'args': {'destination': 'Сон-Куль'},
                        'id': 'search-1',
                        'type': 'tool_call',
                    }
                ],
            ),
            AIMessageChunk(
                content='',
                tool_calls=[
                    {
                        'name': 'get_catalogue_item',
                        'args': {'kind': 'tour', 'id': 7},
                        'id': 'item-1',
                        'type': 'tool_call',
                    }
                ],
            ),
            AIMessageChunk(content='На фото озеро Сон-Куль. Это тур «Сон-Куль»: 3 дня, юрты.'),
        ]
    )
    seen = []

    async def fake_stream(messages):
        seen.append(list(messages))
        yield next(replies)

    calls = []
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=fake_stream))
    monkeypatch.setattr(
        agent,
        'tool_map',
        {
            'search_catalogue': SimpleNamespace(
                invoke=lambda args: (
                    calls.append(('search', args))
                    or {'items': [{'kind': 'tour', 'id': 7, 'title': 'Сон-Куль'}], 'total': 1}
                )
            ),
            'get_catalogue_item': SimpleNamespace(
                invoke=lambda args: (
                    calls.append(('item', args))
                    or {'kind': 'tour', 'id': 7, 'title': 'Сон-Куль', 'duration_days': 3}
                )
            ),
        },
    )
    answer, _, _ = asyncio.run(
        agent._respond(message='[фото]', state={}, history=[], image=b'webp-bytes')
    )

    assert calls == [('search', {'destination': 'Сон-Куль'}), ('item', {'kind': 'tour', 'id': 7})]
    assert 'Сон-Куль' in answer
    # The photo stays attached to the client turn through every tool round.
    assert all(any(m.content == PHOTO_PROMPT for m in round_) for round_ in seen)
    assert len(seen) == 3


def test_photo_turn_allows_extra_tool_rounds(monkeypatch):
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [])
    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=AsyncMock(return_value={})))
    rounds = []

    async def fake_stream(messages):
        rounds.append(1)
        if len(rounds) <= 6:
            yield AIMessageChunk(
                content='',
                tool_calls=[
                    {
                        'name': 'search_catalogue',
                        'args': {},
                        'id': f'search-{len(rounds)}',
                        'type': 'tool_call',
                    }
                ],
            )
        else:
            yield AIMessageChunk(content='Нашёл похожий тур.')

    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=fake_stream))
    monkeypatch.setattr(
        agent, 'tool_map', {'search_catalogue': SimpleNamespace(invoke=lambda args: {'items': []})}
    )
    answer, _, _ = asyncio.run(
        agent._respond(message='[фото]', state={}, history=[], image=b'webp-bytes')
    )
    assert answer == 'Нашёл похожий тур.'
    assert len(rounds) == 7
