"""The agent sends reply text piece by piece while the model writes it."""

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML.errors import AIError


class Listener:
    """Records what the client would see: deltas and resets, in order."""

    def __init__(self):
        self.events = []

    async def __call__(self, text):
        self.events.append(('delta', text))

    async def reset(self):
        self.events.append(('reset', None))

    def visible(self):
        text = ''
        for kind, value in self.events:
            text = '' if kind == 'reset' else text + value
        return text


def runtime(monkeypatch, rounds):
    """Each round is a list of chunks the model streams for one call."""
    agent = importlib.import_module('ML.agent')
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [7])
    calls = iter(rounds)

    async def extract(prompt):
        return agent.Changes()

    async def stream(messages):
        for chunk in next(calls):
            yield chunk
            await asyncio.sleep(0)

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    return agent


def test_pieces_reach_the_client_before_the_model_finishes(monkeypatch):
    agent = importlib.import_module('ML.agent')
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [7])
    listener = Listener()
    seen_while_streaming = []

    async def extract(prompt):
        return agent.Changes()

    async def stream(messages):
        for piece in ('Иссык-Куль ', 'летом ', 'тёплый.'):
            yield AIMessageChunk(content=piece)
            # The next piece is produced only after the previous one was sent.
            seen_while_streaming.append(listener.visible())

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))

    answer, _, _ = asyncio.run(agent.respond('Какая погода?', {}, [], on_chunk=listener))

    assert seen_while_streaming == ['Иссык-Куль ', 'Иссык-Куль летом ', 'Иссык-Куль летом тёплый.']
    assert listener.events == [('delta', 'Иссык-Куль '), ('delta', 'летом '), ('delta', 'тёплый.')]
    assert answer == 'Иссык-Куль летом тёплый.'


def test_preamble_before_a_tool_call_is_withdrawn(monkeypatch):
    agent = runtime(
        monkeypatch,
        [
            [
                AIMessageChunk(content='Непроверенная цена 999. '),
                AIMessageChunk(
                    content='',
                    tool_calls=[
                        {'name': 'read_catalogue', 'args': {}, 'id': 'c-1', 'type': 'tool_call'}
                    ],
                ),
            ],
            [AIMessageChunk(content='Есть подходящий тур. '), AIMessageChunk(content='Даты?')],
        ],
    )
    monkeypatch.setattr(
        agent, 'tool_map', {'read_catalogue': SimpleNamespace(invoke=lambda args: {'ok': True})}
    )
    listener = Listener()

    answer, _, _ = asyncio.run(agent.respond('Подберите тур', {}, [], on_chunk=listener))

    assert ('reset', None) in listener.events
    assert listener.visible() == answer == 'Есть подходящий тур. Даты?'
    assert '999' not in listener.visible()


def test_cut_off_answer_is_withdrawn_before_the_compact_retry(monkeypatch):
    agent = runtime(
        monkeypatch,
        [
            [
                AIMessageChunk(content='Длинная программа '),
                AIMessageChunk(content='', response_metadata={'finish_reason': 'MAX_TOKENS'}),
            ],
            [AIMessageChunk(content='Кратко: 3 дня. Подходит?')],
        ],
    )
    listener = Listener()

    answer, _, _ = asyncio.run(agent.respond('Расскажите', {}, [], on_chunk=listener))

    assert listener.events[:2] == [('delta', 'Длинная программа '), ('reset', None)]
    assert listener.visible() == answer == 'Кратко: 3 дня. Подходит?'


def test_failed_reply_leaves_the_reset_to_the_caller(monkeypatch):
    agent = runtime(
        monkeypatch,
        [
            [
                AIMessageChunk(
                    content='частичный текст', response_metadata={'finish_reason': 'SAFETY'}
                )
            ]
        ],
    )
    listener = Listener()

    with pytest.raises(AIError) as failure:
        asyncio.run(agent.respond('Вопрос', {}, [], on_chunk=listener))

    assert failure.value.code == 'ai_blocked'
    # The chat layer calls reset() on every error before reporting it.
    assert listener.events == [('delta', 'частичный текст')]


def test_plain_callback_still_gets_only_the_final_answer(monkeypatch):
    agent = runtime(
        monkeypatch,
        [
            [
                AIMessageChunk(content='Черновик'),
                AIMessageChunk(content='', response_metadata={'finish_reason': 'MAX_TOKENS'}),
            ],
            [AIMessageChunk(content='Итог. '), AIMessageChunk(content='Вопрос?')],
        ],
    )
    delivered = []

    async def plain(text):
        delivered.append(text)

    answer, _, _ = asyncio.run(agent.respond('Расскажите', {}, [], on_chunk=plain))

    assert delivered == ['Итог. ', 'Вопрос?']
    assert answer == 'Итог. Вопрос?'
