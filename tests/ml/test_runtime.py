"""ML contracts runnable with --confcutdir=tests/ml, without DB or Gemini access."""

import asyncio
import importlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML.translation import translate_fields as translate


def runtime(monkeypatch, replies, changes=None):
    agent = importlib.import_module('ML.agent')
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [7])

    async def extract(prompt):
        return changes if changes is not None else agent.Changes()

    async def stream(messages):
        value = next(replies)
        if isinstance(value, Exception):
            raise value
        yield value

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    return agent


def test_import_does_not_require_database_or_construct_gemini_clients(tmp_path):
    # A constructor trap catches eager initialization even if a key exists in .env.
    code = """
import langchain_google_genai
def forbidden(*args, **kwargs):
    raise AssertionError('Gemini constructed during import')
langchain_google_genai.ChatGoogleGenerativeAI = forbidden
import ML.agent, ML.translation
assert 'mysite.database.db' not in __import__('sys').modules
"""
    env = dict(os.environ)
    env.pop('DATABASE_URL', None)
    result = subprocess.run(
        [sys.executable, '-B', '-c', code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('reason', ['SAFETY', 'RECITATION', 'PROHIBITED_CONTENT', 'SPII'])
def test_blocked_generation_does_not_publish_partial_answer(monkeypatch, reason):
    agent = runtime(
        monkeypatch,
        iter(
            [
                AIMessageChunk(
                    content='partial private text', response_metadata={'finish_reason': reason}
                )
            ]
        ),
    )
    from ML.errors import AIError

    delivered = []

    async def chunk(text):
        delivered.append(text)

    with pytest.raises(AIError) as error:
        asyncio.run(agent.respond('Подберите тур', {}, [], on_chunk=chunk))
    assert error.value.code == 'ai_blocked'
    assert not delivered


def test_invalid_tool_call_is_not_treated_as_a_successful_answer(monkeypatch):
    agent = runtime(
        monkeypatch,
        iter(
            [
                AIMessageChunk(
                    content='all done',
                    invalid_tool_calls=[
                        {
                            'name': 'get_tour_details',
                            'args': '{broken',
                            'id': 'bad',
                            'error': 'invalid JSON',
                        }
                    ],
                )
            ]
        ),
    )
    from ML.errors import AIError

    with pytest.raises(AIError) as error:
        asyncio.run(agent.respond('Тур 7', {}, []))
    assert error.value.code == 'ai_invalid_response'


@pytest.mark.parametrize(
    ('status', 'code'),
    [(429, 'ai_rate_limit'), (503, 'ai_unavailable'), (504, 'ai_timeout'), (403, 'ai_unavailable')],
)
def test_sdk_errors_use_status_and_do_not_expose_provider_text(status, code):
    from google.genai.errors import APIError

    from ML.errors import classify_error

    inner = APIError(status, {'error': {'message': 'secret key and customer message'}})
    outer = RuntimeError('wrapped')
    outer.__cause__ = inner
    failure = classify_error(outer)
    assert failure.code == code
    assert 'secret' not in failure.message


def test_tool_call_budget_rejects_batch_before_executing_tools(monkeypatch):
    calls = [
        {'name': 'get_tour_details', 'args': {'tour_id': 7}, 'id': f'tool-{i}', 'type': 'tool_call'}
        for i in range(20)
    ]
    agent = runtime(monkeypatch, iter([AIMessageChunk(content='', tool_calls=calls)]))
    from ML.errors import AIError

    def unexpected(args):
        raise AssertionError('Over-budget tools must not execute')

    monkeypatch.setattr(agent, 'tool_map', {'get_tour_details': SimpleNamespace(invoke=unexpected)})
    with pytest.raises(AIError):
        asyncio.run(agent.respond('Тур 7', {}, []))


def test_success_preserves_language_preferences_and_does_not_mutate_input(monkeypatch):
    agent = runtime(
        monkeypatch,
        iter(
            [
                AIMessageChunk(
                    content='Welche Termine passen?', response_metadata={'finish_reason': 'STOP'}
                )
            ]
        ),
    )
    original = {
        'language': 'de',
        'people_count': 3,
        'notes': 'Zwei Erwachsene, ein Kind (8 Jahre).',
    }
    answer, updated, intent = asyncio.run(agent.respond('Noch keine Termine', original, []))
    assert answer == 'Welche Termine passen?'
    assert updated == original
    assert updated is not original
    assert intent is False


@pytest.mark.parametrize(
    ('language', 'answer'),
    [
        ('ru', 'Какие даты?'),
        ('ky', 'Кайсы күндөрү?'),
        ('en', 'Which dates?'),
        ('de', 'Welche Termine?'),
        ('zh', '什么日期？'),
    ],
)
def test_extracted_corrections_preserve_other_preferences_in_each_language(
    monkeypatch, language, answer
):
    from ML.schemas import Changes

    agent = runtime(
        monkeypatch,
        iter([AIMessageChunk(content=answer)]),
        Changes(language=language, people_count=4, clear_fields=['email']),
    )
    original = {
        'language': 'ru',
        'people_count': 2,
        'email': 'old@example.com',
        'notes': 'Дети 4 и 9 лет, нужно детское кресло',
        'budget': '1500 USD на всех',
    }
    _, updated, intent = asyncio.run(
        agent.respond('Исправьте число на 4 и удалите email', original, [])
    )
    assert updated == {
        'language': language,
        'people_count': 4,
        'notes': original['notes'],
        'budget': original['budget'],
    }
    assert original['email'] == 'old@example.com'
    assert intent is False


def test_extraction_failure_preserves_data_and_does_not_log_provider_text(monkeypatch, caplog):
    from google.genai.errors import APIError

    agent = runtime(monkeypatch, iter([AIMessageChunk(content='Уточните даты')]))

    async def extract(prompt):
        raise APIError(429, {'error': {'message': 'private-customer-phone secret-api-key'}})

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    original = {'client_name': 'Анна', 'phone': '+996700000001', 'notes': 'Не удалять'}
    _, updated, intent = asyncio.run(agent.respond('Хочу оформить', original, []))
    assert updated == original and intent is False
    assert 'secret-api-key' not in caplog.text
    assert 'private-customer-phone' not in caplog.text


def test_translation_accepts_gemini_text_blocks(monkeypatch):
    from ML import translation

    body = json.dumps({lang: {'title': f'Name {lang}'} for lang in ('en', 'de', 'zh')})
    monkeypatch.setattr(
        translation,
        'model',
        SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content=[{'type': 'text', 'text': body}],
                response_metadata={'finish_reason': 'STOP'},
            )
        ),
    )
    result = translate({'title': 'Название'})
    assert result['en']['title'] == 'Name en'


def test_blocked_translation_does_not_return_partial_output(monkeypatch):
    from ML import translation
    from ML.errors import AIError

    body = json.dumps({lang: {'title': 'Partial'} for lang in ('en', 'de', 'zh')})
    monkeypatch.setattr(
        translation,
        'model',
        SimpleNamespace(
            invoke=lambda messages: SimpleNamespace(
                content=body, response_metadata={'finish_reason': 'SAFETY'}
            )
        ),
    )
    with pytest.raises(AIError):
        translate({'title': 'Название'})


def test_gemini_deadline_error_during_generation_is_safe(monkeypatch):
    from google.genai.errors import APIError

    from ML.errors import AIError

    agent = runtime(monkeypatch, iter([APIError(504, {'error': {'message': 'private request'}})]))
    with pytest.raises(AIError) as failure:
        asyncio.run(agent.respond('Hello', {}, []))
    assert failure.value.code == 'ai_timeout'


def test_cancelled_generation_is_not_retried(monkeypatch):
    agent = runtime(monkeypatch, iter([]))
    attempts = 0

    async def stream(messages):
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError()
        yield

    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent.respond('Hello', {}, []))
    assert attempts == 1


def test_invalid_extraction_is_atomic_and_does_not_create_booking_intent(monkeypatch):
    agent = runtime(
        monkeypatch,
        iter([AIMessageChunk(content='Уточните количество участников')]),
        {
            'client_name': 'Новое имя',
            'people_count': -1,
            'booking_intent': True,
            'clear_fields': ['email'],
        },
    )
    original = {'client_name': 'Анна', 'email': 'keep@example.com', 'people_count': 2}
    _, updated, intent = asyncio.run(agent.respond('Исправьте заявку', original, []))
    assert updated == original
    assert intent is False


@pytest.mark.parametrize('valid', [False, True])
def test_explicit_tour_outside_bounded_catalogue_is_checked_by_exact_id(monkeypatch, valid):
    from ML.schemas import Changes

    agent = runtime(
        monkeypatch, iter([AIMessageChunk(content='Уточним даты')]), Changes(tour_id=999)
    )
    monkeypatch.setattr(agent, 'valid_selected_tour', lambda identity: valid and identity == 999)
    _, updated, _ = asyncio.run(agent.respond('Выбираю ранее предложенный тур 999', {}, []))
    assert updated.get('tour_id') == (999 if valid else None)
