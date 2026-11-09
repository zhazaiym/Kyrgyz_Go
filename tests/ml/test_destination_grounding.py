import pytest

from ML.grounding import destination_is_trusted, grounded
from tests.ml.test_agent_memory import run_agent


@pytest.mark.parametrize(
    'value,text',
    [
        ('Иссык-Куль', 'Хочу поехать на Иссык-Куль'),
        ('Иссык-Куль', 'Хочу отдохнуть на Иссык-Куле'),
        ('Иссык-Куль', 'I want to go to Issyk-Kul'),
        ('Каракол', 'Давайте лучше в Караколе'),
        ('Сон-Куль', 'озеро Сон-Кёль'),
        ('Нарын', 'We want to visit Naryn'),
    ],
)
def test_destination_written_by_client_is_grounded(value, text):
    assert grounded(value, text)


@pytest.mark.parametrize(
    'value,text', [('Иссуй-Буйл', 'Хочу поехать на Иссык-Куль'), ('Бишкек', 'Хочу в Каракол')]
)
def test_destination_the_client_never_wrote_is_not_grounded(value, text):
    assert not grounded(value, text)


@pytest.mark.parametrize(
    'text,language',
    [('Ысык-Көлгө баргым келет', None), ('我想去伊塞克湖', None), ('Барам', 'ky'), ('去', 'zh')],
)
def test_kyrgyz_and_chinese_names_are_not_compared(text, language):
    assert destination_is_trusted('Иссык-Куль', text, language)


def test_garbled_destination_keeps_the_collected_one(monkeypatch):
    state = {'destination': 'Иссык-Куль', 'people_count': 2, 'language': 'ru'}
    _, updated, _ = run_agent(
        monkeypatch,
        state,
        {'destination': 'Иссуй-Буйл', 'budget': '800 долларов'},
        message='Нас 2 человека, бюджет 800 долларов',
    )
    assert updated['destination'] == 'Иссык-Куль'
    assert updated['budget'] == '800 долларов'


def test_garbled_first_destination_is_not_stored(monkeypatch):
    _, updated, _ = run_agent(
        monkeypatch, {}, {'destination': 'Иссуй-Буйл'}, message='Хочу поехать на Иссык-Куль'
    )
    assert 'destination' not in updated
