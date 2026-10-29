"""Exercise the installed LangChain + Gemini HTTP stack, with no network sockets."""

import asyncio

import httpx
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from tests.ml.test_runtime import runtime


@pytest.mark.parametrize(
    ('status', 'code'),
    [(429, 'ai_rate_limit'), (503, 'ai_unavailable'), (504, 'ai_timeout'), (403, 'ai_unavailable')],
)
def test_real_sdk_streaming_errors_are_normalized_without_network(monkeypatch, status, code):
    from ML.errors import AIError

    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status,
            json={
                'error': {
                    'code': status,
                    'message': 'secret-server-details',
                    'status': {
                        429: 'RESOURCE_EXHAUSTED',
                        503: 'UNAVAILABLE',
                        504: 'DEADLINE_EXCEEDED',
                        403: 'PERMISSION_DENIED',
                    }[status],
                }
            },
        )

    agent = runtime(monkeypatch, iter([]))
    model = ChatGoogleGenerativeAI(
        model='gemini-3.5-flash-lite',
        api_key='offline-key',
        max_retries=0,
        client_args={'transport': httpx.MockTransport(handle)},
    )
    monkeypatch.setattr(agent, 'agent_llm', model)
    try:
        with pytest.raises(AIError) as failure:
            asyncio.run(agent.respond('Какие туры?', {}, []))
        assert failure.value.code == code
        assert 'secret-server-details' not in failure.value.message
        assert len(requests) == 1
        assert requests[0].url.path.endswith(':streamGenerateContent')
    finally:
        model.client.close()
