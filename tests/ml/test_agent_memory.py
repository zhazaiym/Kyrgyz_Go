import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessageChunk

import ML.agent as agent


def run_agent(monkeypatch, state, changes, message='Сообщение клиента'):
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [7, 8])

    monkeypatch.setattr(
        agent, 'extractor', SimpleNamespace(ainvoke=AsyncMock(return_value=changes))
    )

    async def fake_stream(messages):
        yield AIMessageChunk(content='Хорошо!')

    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=fake_stream))

    return asyncio.run(agent._respond(message=message, state=state, history=[]))


def test_memory_keeps_existing_fields(monkeypatch):
    state = {
        'client_name': 'Алина',
        'people_count': 4,
        'budget': '50000 сом',
        'destination': 'Иссык-Куль',
    }

    _, updated, _ = run_agent(monkeypatch, state, {'travel_date': '2026-12-15'})

    assert updated['client_name'] == 'Алина'
    assert updated['people_count'] == 4
    assert updated['budget'] == '50000 сом'
    assert updated['destination'] == 'Иссык-Куль'
    assert updated['travel_date'] == '2026-12-15'


def test_comparison_keeps_selected_tour(monkeypatch):
    state = {'tour_id': 7, 'people_count': 4}

    _, updated, _ = run_agent(
        monkeypatch, state, {'destination': 'Каракол'}, message='А чем отличается от Каракола?'
    )

    assert updated['tour_id'] == 7
    assert 'destination' not in updated


def test_explicit_destination_change(monkeypatch):
    state = {'tour_id': 7, 'people_count': 4}

    _, updated, _ = run_agent(
        monkeypatch,
        state,
        {'destination': 'Каракол', 'clear_fields': ['tour_id']},
        message='Нет, давайте лучше в Каракол',
    )

    assert 'tour_id' not in updated
    assert updated['destination'] == 'Каракол'
    assert updated['people_count'] == 4
