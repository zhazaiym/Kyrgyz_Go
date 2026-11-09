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


@pytest.mark.parametrize('fail', [False, True])
def test_response_writes_one_timing_summary_including_failed_phases(monkeypatch, caplog, fail):
    async def invoke():
        if fail:
            raise RuntimeError('private details')
        return ('Answer', {}, False)

    async def respond(*args):
        return await agent._measured_call('extractor', invoke, timeout=1)

    monkeypatch.setattr(agent, '_respond', respond)
    with caplog.at_level(logging.INFO, logger='ML.agent'):
        if fail:
            with pytest.raises(RuntimeError):
                asyncio.run(agent.respond('Private question', {}, []))
        else:
            asyncio.run(agent.respond('Private question', {}, []))
    entries = [item for item in caplog.records if item.levelno == logging.INFO]
    assert len(entries) == 1
    assert 'AI response outcome=' in entries[0].message
    assert 'extractor' in entries[0].message
    assert ('failure' if fail else 'success') in entries[0].message
    assert 'Private question' not in caplog.text
    assert 'private details' not in caplog.text


def test_model_receives_one_catalogue_tool_schema():
    names = {tool.name for tool in agent.READ_TOOLS}
    assert {'search_catalogue', 'get_catalogue_item'} <= names
    assert not {'search_tours', 'list_active_tours', 'get_tour_details'} & names
