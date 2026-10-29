import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML.errors import AIError
from tests.ml.test_runtime import runtime


@pytest.mark.parametrize('payload_type', ['reasoning', 'tool_args'])
def test_oversized_non_text_payload_is_rejected_before_tools_or_publication(
    monkeypatch, payload_type
):
    if payload_type == 'reasoning':
        reply = AIMessageChunk(
            content=[
                {'type': 'reasoning', 'reasoning': 'x' * 1_100_000},
                {'type': 'text', 'text': 'OK'},
            ],
            response_metadata={'finish_reason': 'STOP'},
        )
    else:
        reply = AIMessageChunk(
            content='',
            tool_calls=[
                {
                    'name': 'get_tour_details',
                    'args': {'tour_id': '9' * 1_100_000},
                    'id': 'oversized-call',
                    'type': 'tool_call',
                }
            ],
        )
    agent = runtime(monkeypatch, iter([reply]))

    def must_not_execute(args):
        raise AssertionError('Oversized model payload reached a tool')

    monkeypatch.setattr(
        agent, 'tool_map', {'get_tour_details': SimpleNamespace(invoke=must_not_execute)}
    )
    delivered = []

    async def chunk(text):
        delivered.append(text)

    with pytest.raises(AIError) as failure:
        asyncio.run(agent.respond('Какие туры?', {}, [], on_chunk=chunk))
    assert failure.value.code == 'ai_invalid_response'
    assert not delivered
