"""Server-owned recognition of explicit booking confirmation and rejection."""

import re

CONFIRMATION_TEXT = 'подтверждаю заявку'
CONFIRMATION_REPLIES = {
    'да подтверждаю',
    'подтверждаю',
    CONFIRMATION_TEXT,
    'я готова бронировать тур',
    'я готов бронировать тур',
    'я готова бронировать туры',
    'я готов бронировать туры',
    'я готова забронировать тур',
    'я готов забронировать тур',
    'yes confirm',
    'i confirm',
    'confirm',
    'confirm request',
    'ооба ырастайм',
    'ырастайм',
    'өтүнмөнү ырастайм',
    'ich bestätige',
    'ich bestätige die anfrage',
    '确认提交',
    '确认申请',
}
REJECTION_REPLIES = {
    'нет',
    'не подтверждаю',
    'не отправляй',
    'отмена',
    'нет спасибо',
    'не отправляйте',
    'не отправляйте заявку',
    'пока не отправляй',
    'пока не отправляйте',
    'не оформляй',
    'не оформляйте',
    'не хочу бронировать',
    'я передумал',
    'я передумала',
    'я передумал бронировать',
    'я передумала бронировать',
    'no',
    'no thanks',
    'not now',
    'do not submit',
    'do not send yet',
    'don t send yet',
    'cancel',
    'cancel request',
    'жок',
    'жок рахмат',
    'ырастабайм',
    'жөнөтпө',
    'азыр жөнөтпө',
    'nein',
    'nicht absenden',
    '不发送',
    '取消',
}


def normalized_reply(message: str) -> str:
    return ' '.join(re.sub(r'[^\w\s]', ' ', message.casefold()).split())


def confirmation_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and normalized_reply(message) in CONFIRMATION_REPLIES


def rejection_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and normalized_reply(message) in REJECTION_REPLIES
