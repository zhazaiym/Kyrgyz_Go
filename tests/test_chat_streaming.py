"""The chat WebSocket streams the assistant reply piece by piece."""

from ML.errors import AIError
from mysite.api import chat_service
from tests.test_chat_booking_flow import complete_state, start_chat


def exchange(client, token, session_id, message):
    events = []
    with client.websocket_connect(
        f'/ws/chat/{session_id}', headers={'origin': 'http://localhost:3000'}
    ) as websocket:
        websocket.send_json({'type': 'auth', 'token': token})
        assert websocket.receive_json()['type'] == 'connected'
        websocket.send_json({'type': 'message', 'message': message})
        while True:
            event = websocket.receive_json()
            events.append(event)
            if event['type'] == 'typing' and event['status'] is False:
                return events


def shown_text(events):
    """Apply deltas and resets the way the frontend does."""
    text = ''
    for event in events:
        if event['type'] == 'message_reset':
            text = ''
        elif event['type'] == 'message_delta':
            text += event['delta']
    return text


def history(client, token, session_id):
    response = client.get(
        f'/chat/history/{session_id}', headers={'Authorization': f'Bearer {token}'}
    )
    assert response.status_code == 200, response.text
    return [item['content'] for item in response.json() if item['role'] == 'assistant']


def test_reply_arrives_as_several_deltas_in_order(client, monkeypatch):
    token, _, session_id = start_chat(client, 'stream_pieces')
    pieces = ['Иссык-Куль ', 'летом ', 'тёплый. ', 'Когда планируете поездку?']

    async def reply(message, state, history, on_chunk=None):
        for piece in pieces:
            await on_chunk(piece)
        return ''.join(pieces).strip(), state, False

    monkeypatch.setattr(chat_service, 'respond', reply)
    events = exchange(client, token, session_id, 'Какая там погода?')

    kinds = [event['type'] for event in events]
    assert kinds[:2] == ['typing', 'message_start']
    deltas = [event for event in events if event['type'] == 'message_delta']
    assert [event['delta'] for event in deltas] == pieces
    message_id = events[1]['message_id']
    assert all(event['message_id'] == message_id for event in deltas)
    assert kinds.index('message_end') > kinds.index('message_delta')
    assert 'message_reset' not in kinds
    assert shown_text(events) == ''.join(pieces)
    assert history(client, token, session_id)[-1] == ''.join(pieces).strip()


def test_server_summary_replaces_the_streamed_model_text(client, monkeypatch):
    token, _, session_id = start_chat(client, 'stream_summary')

    async def reply(message, state, history, on_chunk=None):
        await on_chunk('Модельная ')
        await on_chunk('сводка.')
        return 'Модельная сводка.', complete_state(), True

    monkeypatch.setattr(chat_service, 'respond', reply)
    events = exchange(client, token, session_id, 'Оформить')

    kinds = [event['type'] for event in events]
    assert 'message_reset' in kinds
    assert kinds.index('message_reset') < kinds.index('message_end')
    final = shown_text(events)
    assert 'Модельная' not in final
    assert 'Подтверждаете отправку' in final
    assert history(client, token, session_id)[-1] == final


def test_error_withdraws_text_already_streamed(client, monkeypatch):
    token, _, session_id = start_chat(client, 'stream_error')

    async def reply(message, state, history, on_chunk=None):
        await on_chunk('Частичный ответ')
        raise AIError('ai_blocked')

    monkeypatch.setattr(chat_service, 'respond', reply)
    events = exchange(client, token, session_id, 'Вопрос')

    kinds = [event['type'] for event in events]
    assert kinds.index('message_delta') < kinds.index('message_reset') < kinds.index('error')
    assert next(event for event in events if event['type'] == 'error')['code'] == 'ai_blocked'
    assert shown_text(events) == ''
    assert 'Частичный ответ' not in history(client, token, session_id)
