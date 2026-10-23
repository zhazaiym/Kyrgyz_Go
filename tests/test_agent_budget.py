import asyncio
import os
from types import SimpleNamespace

from langchain_core.messages import AIMessageChunk
import pytest

from mysite.chain import agent


def fake_runtime(monkeypatch, replies, changes=None):
    seen = {'messages': [], 'extraction': []}

    async def extract(prompt):
        seen['extraction'].append(prompt)
        return changes or agent.Changes()

    async def stream(messages):
        seen['messages'].append(list(messages))
        yield replies[len(seen['messages']) - 1]

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    return seen


def test_chat_models_have_separate_output_budgets():
    assert agent.llm.max_output_tokens == max(256, min(4096, int(os.getenv('CHAT_MAX_OUTPUT_TOKENS', '1536'))))
    assert agent.extract_llm.max_output_tokens == max(256, min(1024, int(os.getenv('CHAT_EXTRACT_MAX_OUTPUT_TOKENS', '512'))))


@pytest.mark.parametrize(('configured', 'expected'), [('999999', 4096), ('1', 256), ('1536', 1536)])
def test_response_budget_has_hard_bounds(monkeypatch, configured, expected):
    monkeypatch.setenv('CHAT_MAX_OUTPUT_TOKENS', configured)
    assert agent.output_budget('CHAT_MAX_OUTPUT_TOKENS', 1536, 4096) == expected


def test_extractor_receives_previous_question_for_short_answers(monkeypatch):
    seen = fake_runtime(monkeypatch, [AIMessageChunk(content='Анна, на какую дату планируете поездку?')],
                        changes=agent.Changes(client_name='Анна'))
    history = [SimpleNamespace(role='assistant', content='Как к вам обращаться?')]
    answer, updated, intent = asyncio.run(agent.respond('Анна', {}, history))
    assert 'Как к вам обращаться?' in seen['extraction'][0]
    assert updated['client_name'] == 'Анна'
    assert not intent


def test_prompt_contains_detailed_consultation_policy():
    from mysite.chain.prompts import SYSTEM_PROMPT, EXTRACT_PROMPT

    assert sum(bool(line.strip()) for line in SYSTEM_PROMPT.splitlines()) >= 1000
    assert '2–5 содержательных предложений' not in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.format(state='{}', today='2026-10-23')
    assert EXTRACT_PROMPT.format(state='{}', tour_ids='[]', message='Анна', context='[]')


def test_extraction_context_keeps_last_question_with_a_fixed_size():
    history = [SimpleNamespace(role='assistant', content='Подробное объяснение. ' * 500
                              + 'Какой номер телефона указать?')]
    context = agent.extraction_context(history)
    assert 'Какой номер телефона указать?' in context
    assert len(context) < 2600


def test_history_context_is_bounded_and_keeps_recent_turns(monkeypatch):
    seen = fake_runtime(monkeypatch, [AIMessageChunk(content='Короткий ответ.')])
    history = [SimpleNamespace(role='user', content=f'Old preference {index}: ' + 'x' * 1400)
               for index in range(30)]
    history.append(SimpleNamespace(role='user', content='Most recent preference'))
    asyncio.run(agent.respond('Текущий вопрос', {}, history))
    context = seen['messages'][0][1:-1]
    assert len(context) <= 12
    assert sum(len(message.content) for message in context) <= 8000
    assert context[-1].content == 'Most recent preference'


def test_extraction_does_not_load_full_tour_programs(monkeypatch):
    seen = fake_runtime(monkeypatch, [AIMessageChunk(content='Здравствуйте!')])

    def full_catalogue_is_not_needed(*args):
        raise AssertionError('Do not load the full catalogue for field extraction')

    monkeypatch.setattr(agent, 'list_active_tours', SimpleNamespace(invoke=full_catalogue_is_not_needed), raising=False)
    asyncio.run(agent.respond('Здравствуйте', {}, []))
    assert len(seen['extraction']) == 1


def test_tool_round_preamble_is_not_sent_to_client(monkeypatch):
    fake_runtime(monkeypatch, [
        AIMessageChunk(content='Непроверенная цена 999.', tool_calls=[{
            'name': 'read_catalogue', 'args': {}, 'id': 'catalogue-1', 'type': 'tool_call',
        }]),
        AIMessageChunk(content='В каталоге есть подходящий тур. Уточним даты?'),
    ])
    monkeypatch.setattr(agent, 'tool_map', {'read_catalogue': SimpleNamespace(invoke=lambda args: {'title': 'Real tour'})})
    delivered = []

    async def chunk(text):
        delivered.append(text)

    answer, _, _ = asyncio.run(agent.respond('Подберите тур', {}, [], on_chunk=chunk))
    assert '999' not in answer
    assert '999' not in ''.join(delivered)
    assert ''.join(delivered) == answer


def test_truncated_response_is_retried_without_publishing_partial_text(monkeypatch):
    seen = fake_runtime(monkeypatch, [
        AIMessageChunk(content='Незаконченная программа первого дня', response_metadata={'finish_reason': 'MAX_TOKENS'}),
        AIMessageChunk(content='Могу кратко описать маршрут. Какая длительность вам подходит?'),
    ])
    delivered = []

    async def chunk(text):
        delivered.append(text)

    answer, _, _ = asyncio.run(agent.respond('Расскажите подробнее', {}, [], on_chunk=chunk))
    assert len(seen['messages']) == 2
    assert 'Незаконченная' not in answer
    assert ''.join(delivered) == answer


def test_repeated_output_exhaustion_does_not_save_partial_answer(monkeypatch):
    fake_runtime(monkeypatch, [
        AIMessageChunk(content='Первый обрыв', response_metadata={'finish_reason': 'MAX_TOKENS'}),
        AIMessageChunk(content='Второй обрыв', response_metadata={'finish_reason': 'MAX_TOKENS'}),
    ])
    with pytest.raises(RuntimeError, match='output budget'):
        asyncio.run(agent.respond('Подробный маршрут', {}, []))
