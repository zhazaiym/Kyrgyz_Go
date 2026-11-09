import pytest

from mysite.api.booking_intent import confirmation_allowed, rejection_allowed

STAGE = 'awaiting_confirmation'


@pytest.mark.parametrize(
    'message',
    [
        'Подтверждаю',
        'Да, отправляйте',
        'Подтверждаю отправку',
        'Да, всё верно, отправьте заявку',
        'Оформляйте',
        'Yes, send it',
        'I confirm',
        'Ооба, ырастайм',
        'Ich bestätige',
        '确认提交',
    ],
)
def test_explicit_confirmations_submit(message):
    assert confirmation_allowed(STAGE, message)
    assert not confirmation_allowed('collecting', message)


@pytest.mark.parametrize(
    'message',
    [
        'Да',
        'ок',
        'Отправить?',
        'Отправьте мне список отелей',
        'Хочу поменять дату и отправить',
        'не отправляйте',
        'Do not submit',
        'Жөнөтпө',
        'Nicht absenden',
        '不发送',
    ],
)
def test_ambiguous_or_negative_replies_do_not_submit(message):
    assert not confirmation_allowed(STAGE, message)


def test_negations_still_reject():
    assert rejection_allowed(STAGE, 'Не отправляйте заявку')


def test_agent_lists_missing_request_fields():
    from ML.agent import missing_for_request

    assert missing_for_request({}) == [
        'тур или направление',
        'точная дата начала поездки',
        'общее число людей',
        'имя',
        'телефон',
    ]
    full = {
        'destination': 'Иссык-Куль',
        'travel_date': '2099-06-01',
        'people_count': 2,
        'client_name': 'Анна',
        'phone': '+996700111222',
    }
    assert missing_for_request(full) == []


def test_agent_flags_past_travel_date():
    from ML.agent import missing_for_request

    state = {
        'destination': 'Иссык-Куль',
        'travel_date': '2020-06-20',
        'people_count': 2,
        'client_name': 'Анна',
        'phone': '+996700111222',
    }
    assert missing_for_request(state) == [
        'дата поездки в будущем (прошедшая или неверная не подходит)'
    ]


def test_not_ready_text_names_fields_in_client_language():
    from mysite.api.booking_text import not_ready_text

    assert 'телефон' in not_ready_text({'language': 'ru'}, ['phone'])
    assert 'phone' in not_ready_text({'language': 'en'}, ['phone'])
