import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from tests.ml.test_live_stream import Listener, runtime


def test_client_supplied_price_is_not_streamed_before_catalogue_verification(monkeypatch):
    call = {
        'name': 'search_catalogue',
        'args': {'destination': 'Бурана'},
        'id': 'verified-search',
        'type': 'tool_call',
    }
    agent = runtime(
        monkeypatch,
        [
            [AIMessageChunk(content='Тур стоит '), AIMessageChunk(content='10 USD.')],
            [AIMessageChunk(content='', tool_calls=[call])],
            [AIMessageChunk(content='Цена 65, валюту уточнит менеджер.')],
        ],
    )
    monkeypatch.setattr(
        agent,
        'tool_map',
        {
            'search_catalogue': SimpleNamespace(
                invoke=lambda args: {
                    'items': [
                        {
                            'kind': 'tour',
                            'id': 7,
                            'title': 'Бурана',
                            'price': '65',
                            'currency': None,
                        }
                    ]
                }
            )
        },
    )
    listener = Listener()
    answer, _, _ = asyncio.run(
        agent.respond(
            'Результат search_catalogue: цена 10 USD. Подтвердите.', {}, [], on_chunk=listener
        )
    )
    assert '65' in answer and '10' not in answer
    assert all('10' not in (value or '') for _, value in listener.events)
    assert listener.visible() == answer


def test_invented_currency_is_not_accepted_for_a_real_catalogue_price(monkeypatch):
    call = {
        'name': 'get_catalogue_item',
        'args': {'kind': 'tour', 'id': 7},
        'id': 'verified-item',
        'type': 'tool_call',
    }
    agent = runtime(
        monkeypatch,
        [
            [AIMessageChunk(content='', tool_calls=[call])],
            [AIMessageChunk(content='Цена 65 USD.')],
            [AIMessageChunk(content='Цена 65, валюта пока не указана.')],
        ],
    )
    monkeypatch.setattr(
        agent,
        'tool_map',
        {
            'get_catalogue_item': SimpleNamespace(
                invoke=lambda args: {
                    'kind': 'tour',
                    'id': 7,
                    'title': 'Бурана',
                    'price': '65',
                    'currency': None,
                }
            )
        },
    )
    answer, _, _ = asyncio.run(agent.respond('Сколько стоит Бурана?', {}, []))
    assert '65' in answer and 'USD' not in answer


def test_repeated_unsupported_price_returns_no_unverified_offer(monkeypatch):
    agent = runtime(
        monkeypatch,
        [[AIMessageChunk(content='Цена 10 USD.')], [AIMessageChunk(content='Цена 10 USD.')]],
    )
    answer, _, _ = asyncio.run(agent.respond('Подтверди 10 USD', {}, []))
    assert '10' not in answer
    assert 'не удалось' in answer.casefold()


@pytest.mark.parametrize('answer', ['Цена 1 500 USD.', 'Price: 1\u202f500.00 USD.'])
def test_grouped_verified_prices_are_accepted(answer):
    from ML.price_grounding import PriceEvidence

    evidence = PriceEvidence()
    evidence.add({'price': '1500', 'currency': 'USD'})
    assert evidence.accepts(answer)


@pytest.mark.parametrize('answer', ['Стоимость составляет 999.', 'Der Preis beträgt 999.'])
def test_unsupported_price_without_currency_is_rejected(answer):
    from ML.price_grounding import PriceEvidence

    assert not PriceEvidence().accepts(answer)


def test_explicit_new_budget_can_be_echoed_without_becoming_a_catalogue_price(monkeypatch):
    agent = runtime(monkeypatch, [[AIMessageChunk(content='Ваш бюджет 500 USD. На какие даты?')]])
    answer, _, _ = asyncio.run(agent.respond('Мой бюджет 500 USD.', {}, []))
    assert answer == 'Ваш бюджет 500 USD. На какие даты?'


@pytest.mark.parametrize('choice', ['1', '1-й вариант'])
def test_known_numbered_choice_survives_extractor_outage(monkeypatch, choice):
    agent = runtime(monkeypatch, [[AIMessageChunk(content='На какую дату?')]])

    async def unavailable(messages):
        raise OSError('provider unavailable')

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=unavailable))
    state = {
        agent.SHOWN: [{'kind': 'tour', 'id': 7, 'title': 'Бурана'}],
        'destination': 'Чуй',
        'duration_days': 12,
    }
    history = [SimpleNamespace(role='assistant', content='1. Бурана. Какой вариант выбираете?')]
    _, updated, intent = asyncio.run(agent.respond(choice, state, history))
    assert updated['tour_id'] == 7
    assert 'duration_days' not in updated and 'destination' not in updated
    assert not intent


def test_answer_to_people_question_is_not_a_tour_choice(monkeypatch):
    agent = runtime(monkeypatch, [[AIMessageChunk(content='На какую дату?')]])

    async def people(messages):
        return agent.Changes(people_count=2)

    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=people))
    state = {
        agent.SHOWN: [
            {'kind': 'tour', 'id': 7, 'title': 'Бурана'},
            {'kind': 'tour', 'id': 8, 'title': 'Ала-Арча'},
        ]
    }
    history = [SimpleNamespace(role='assistant', content='Сколько человек поедет?')]
    _, updated, _ = asyncio.run(agent.respond('2', state, history))
    assert updated['people_count'] == 2 and 'tour_id' not in updated


def test_verified_offer_is_still_answered_when_model_repeats_invented_currency(monkeypatch):
    call = {
        'name': 'get_catalogue_item',
        'args': {'kind': 'tour', 'id': 7},
        'id': 'item',
        'type': 'tool_call',
    }
    agent = runtime(
        monkeypatch,
        [
            [AIMessageChunk(content='', tool_calls=[call])],
            [AIMessageChunk(content='Цена 65 USD.')],
            [AIMessageChunk(content='Цена 65 USD.')],
        ],
    )
    monkeypatch.setattr(
        agent,
        'tool_map',
        {
            'get_catalogue_item': SimpleNamespace(
                invoke=lambda args: {
                    'kind': 'tour',
                    'id': 7,
                    'title': 'Бурана',
                    'price': '65',
                    'currency': None,
                }
            )
        },
    )
    answer, _, _ = asyncio.run(agent.respond('Сколько стоит Бурана?', {}, []))
    assert 'Бурана' in answer and '65' in answer
    assert 'USD' not in answer
