import asyncio

from mysite.api.chat_service import ReplyStream


def stream():
    events = []

    async def send(text):
        events.append(('delta', text))

    async def withdraw():
        events.append(('reset',))

    return ReplyStream(send, withdraw), events


def test_pieces_are_forwarded_and_empty_pieces_are_skipped():
    reply, events = stream()
    for piece in ('При', '', 'вет'):
        asyncio.run(reply(piece))
    assert events == [('delta', 'При'), ('delta', 'вет')]
    assert reply.text == 'Привет'


def test_reset_without_sent_text_sends_nothing():
    reply, events = stream()
    asyncio.run(reply.reset())
    assert events == []


def test_finish_keeps_text_that_already_matches():
    reply, events = stream()
    asyncio.run(reply('Ответ готов. '))
    asyncio.run(reply.finish('Ответ готов.'))
    assert events == [('delta', 'Ответ готов. ')]


def test_finish_replaces_text_the_server_did_not_keep():
    reply, events = stream()
    asyncio.run(reply('Модельная сводка'))
    asyncio.run(reply.finish('Проверьте заявку. Подтверждаете отправку?'))
    assert events == [
        ('delta', 'Модельная сводка'),
        ('reset',),
        ('delta', 'Проверьте заявку. Подтверждаете отправку?'),
    ]
    assert reply.text == 'Проверьте заявку. Подтверждаете отправку?'
