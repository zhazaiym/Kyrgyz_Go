import asyncio
import logging
from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML import agent


@pytest.mark.parametrize('outcome', ['success', 'failure', 'timeout'])
def test_operation_timing_is_recorded_for_every_outcome(monkeypatch, caplog, outcome):
    recorded = []
    monkeypatch.setattr(agent, 'record_ai_call', lambda *args: recorded.append(args))

    async def invoke():
        if outcome == 'failure':
            raise RuntimeError('private provider details')
        if outcome == 'timeout':
            await asyncio.sleep(1)
        return 'ok'

    async def run():
        if outcome == 'success':
            assert await agent._measured_call('extractor', invoke, timeout=0.01) == 'ok'
        else:
            with pytest.raises(RuntimeError if outcome == 'failure' else TimeoutError):
                await agent._measured_call('extractor', invoke, timeout=0.01)

    with caplog.at_level(logging.INFO, logger='ML.agent'):
        asyncio.run(run())
    assert recorded[0][:2] == ('extractor', outcome)
    assert recorded[0][2] >= 0
    assert f'outcome={outcome}' in caplog.text
    assert 'private provider details' not in caplog.text


def test_both_prompts_receive_the_same_bishkek_calendar_date(monkeypatch):
    seen = {}
    monkeypatch.setattr(agent, 'bishkek_today', lambda: date(2026, 11, 7))
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [])

    async def extract(prompt):
        seen['extract'] = prompt
        return agent.Changes(travel_date='2026-11-08')

    async def stream(messages):
        seen['system'] = messages[0].content
        yield AIMessageChunk(content='Уточним поездку на завтра.')

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    _, state, _ = asyncio.run(agent._respond('Поедем завтра', {}, []))
    assert '2026-11-07' in seen['extract']
    assert '2026-11-07' in seen['system']
    assert state['travel_date'] == '2026-11-08'
