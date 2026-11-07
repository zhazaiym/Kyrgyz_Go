import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML.context import recent_messages
from ML.errors import AIError
from tests.ml.test_runtime import runtime


def test_long_latest_reply_keeps_its_final_question_without_mutating_history(monkeypatch):
    monkeypatch.setenv('CHAT_HISTORY_CHARACTERS', '80')
    original = 'Tour description. ' * 100 + 'Which option do you prefer?'
    history = [SimpleNamespace(role='assistant', content=original)]

    selected = recent_messages(history)

    assert len(selected) == 1
    assert selected[0].role == 'assistant'
    assert selected[0].content == original[-80:]
    assert history[0].content == original


def test_history_keeps_recent_turn_and_tail_of_older_reply(monkeypatch):
    monkeypatch.setenv('CHAT_HISTORY_CHARACTERS', '40')
    history = [
        SimpleNamespace(role='assistant', content='x' * 100 + 'Choose a tour?'),
        SimpleNamespace(role='user', content='The second one'),
    ]

    selected = recent_messages(history)

    assert [item.role for item in selected] == ['assistant', 'user']
    assert selected[0].content.endswith('Choose a tour?')
    assert selected[1].content == 'The second one'
    assert sum(len(item.content) for item in selected) == 40


def test_exact_history_budget_never_reintroduces_older_text(monkeypatch):
    monkeypatch.setenv('CHAT_HISTORY_CHARACTERS', '5')
    history = [
        SimpleNamespace(role='assistant', content='Older question'),
        SimpleNamespace(role='user', content='Hello'),
    ]
    assert [item.content for item in recent_messages(history)] == ['Hello']


@pytest.mark.parametrize('empty_stream', [True, False])
def test_empty_provider_output_raises_safe_invalid_response_without_publication(
    monkeypatch, empty_stream
):
    agent = runtime(monkeypatch, iter([]))

    async def stream(messages):
        if not empty_stream:
            yield AIMessageChunk(content='   ', response_metadata={'finish_reason': 'STOP'})

    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    delivered = []

    async def on_chunk(text):
        delivered.append(text)

    with pytest.raises(AIError) as failure:
        asyncio.run(agent.respond('Which tours?', {}, [], on_chunk=on_chunk))
    assert failure.value.code == 'ai_invalid_response'
    assert not delivered
