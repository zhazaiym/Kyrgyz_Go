"""Record and client IDs never reach the client, however the model streams them."""

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk

from ML.agent import IdScrubber


def scrubbed(text, size):
    scrubber = IdScrubber()
    pieces = [scrubber.feed(text[start : start + size]) for start in range(0, len(text), size)]
    return ''.join(pieces) + scrubber.flush()


@pytest.mark.parametrize('size', [1, 2, 3, 7, 1000])
@pytest.mark.parametrize(
    'text',
    [
        'Тур «Ала-Арча» (ID: 12) на 3 дня.',
        'Ваш код клиента KG-000123, отель #7 и транспорт id=4.',
        'Tour ID 15 — Burana; айди 9; ид №3',
    ],
)
def test_ids_are_removed_wherever_the_stream_is_cut(text, size):
    result = scrubbed(text, size)

    assert not any(character.isdigit() for character in result.replace('3 дня', ''))
    assert 'KG-' not in result and '#' not in result


@pytest.mark.parametrize('size', [1, 3, 1000])
def test_ordinary_numbers_and_words_are_kept(size):
    text = 'Поездка на 3 дня для 2 человек, цена 300, телефон +996 555 123456, видео и идеи.'

    assert scrubbed(text, size) == text


def test_reply_from_the_model_reaches_the_client_without_ids(monkeypatch):
    agent = importlib.import_module('ML.agent')
    monkeypatch.setattr(agent, 'active_tour_ids', lambda: [7])
    sent = []

    async def extract(prompt):
        return agent.Changes()

    async def stream(messages):
        for piece in ('Тур «Бурана» (I', 'D: 7), ваш код KG-0', '00042. Едем?'):
            yield AIMessageChunk(content=piece)

    async def listener(text):
        sent.append(text)

    async def reset():
        sent.clear()

    listener.reset = reset
    monkeypatch.setattr(agent, 'extractor', SimpleNamespace(ainvoke=extract))
    monkeypatch.setattr(agent, 'agent_llm', SimpleNamespace(astream=stream))

    answer, _, _ = asyncio.run(agent.respond('Какой ID у тура?', {}, [], on_chunk=listener))

    assert answer == 'Тур «Бурана», ваш код. Едем?'
    assert ''.join(sent).strip() == answer
