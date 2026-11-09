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


# A short reply confirms only when every word is known, at least one is an
# explicit "confirm/send/book" verb, and none is a negation or a question.
# Bare "да"/"ok" stays insufficient; "Да, отправляйте" or "Подтверждаю
# отправку" no longer fall through to the AI, which cannot submit requests.
CONFIRMATION_VERBS = {
    'подтверждаю',
    'подтверждаем',
    'подтвердить',
    'подтвердите',
    'подтверди',
    'отправляйте',
    'отправляй',
    'отправьте',
    'отправь',
    'отправить',
    'оформляйте',
    'оформляй',
    'оформите',
    'оформи',
    'оформить',
    'бронируйте',
    'бронирую',
    'бронируем',
    'забронируйте',
    'забронируй',
    'забронировать',
    'бронировать',
    'передайте',
    'передавайте',
    'confirm',
    'confirmed',
    'submit',
    'send',
    'book',
    'ырастайм',
    'ырастаймын',
    'ырастайбыз',
    'тастыктайм',
    'жөнөтүңүз',
    'жөнөткүлө',
    'жөнөт',
    'жөнөтө',
    'жибериңиз',
    'bestätige',
    'bestätigen',
    'absenden',
    'senden',
    'buchen',
}
CONFIRMATION_WORDS = CONFIRMATION_VERBS | {
    'да',
    'ок',
    'окей',
    'ok',
    'хорошо',
    'все',
    'всё',
    'верно',
    'правильно',
    'отлично',
    'давайте',
    'давай',
    'пожалуйста',
    'можно',
    'я',
    'мы',
    'готов',
    'готова',
    'готовы',
    'заявку',
    'заявка',
    'тур',
    'туры',
    'бронь',
    'отправку',
    'менеджеру',
    'это',
    'данные',
    'yes',
    'okay',
    'sure',
    'please',
    'all',
    'correct',
    'right',
    'good',
    'looks',
    'is',
    'it',
    'i',
    'we',
    'the',
    'request',
    'booking',
    'trip',
    'tour',
    'now',
    'go',
    'ahead',
    'ооба',
    'макул',
    'туура',
    'баары',
    'өтүнмөнү',
    'өтүнмө',
    'бериңиз',
    'бер',
    'ja',
    'gut',
    'alles',
    'korrekt',
    'richtig',
    'bitte',
    'ich',
    'die',
    'anfrage',
    'sie',
}
CHINESE_CONFIRMATIONS = ('确认', '提交', '发送')
CHINESE_NEGATIONS = ('不', '别', '取消', '吗')


def normalized_reply(message: str) -> str:
    return ' '.join(re.sub(r'[^\w\s]', ' ', message.casefold()).split())


def _explicit_confirmation(message: str) -> bool:
    if '?' in message or '？' in message:
        return False
    reply = normalized_reply(message)
    if reply in CONFIRMATION_REPLIES:
        return True
    compact = reply.replace(' ', '')
    if any(word in compact for word in CHINESE_CONFIRMATIONS):
        return len(compact) <= 12 and not any(word in compact for word in CHINESE_NEGATIONS)
    words = reply.split()
    return (
        0 < len(words) <= 8
        and all(word in CONFIRMATION_WORDS for word in words)
        and any(word in CONFIRMATION_VERBS for word in words)
    )


def confirmation_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and _explicit_confirmation(message)


def rejection_allowed(stage: str, message: str) -> bool:
    return stage == 'awaiting_confirmation' and normalized_reply(message) in REJECTION_REPLIES
