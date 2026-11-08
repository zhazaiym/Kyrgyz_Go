import os
from io import BytesIO

import pytest
from PIL import Image

from mysite.api import chat_images, chat_service


@pytest.fixture(autouse=True)
def empty_photo_store():
    chat_images._pending.clear()
    yield
    chat_images._pending.clear()


def register(client, username):
    response = client.post(
        '/chat/auth/register', json={'username': username, 'password': 'StrongPassword123!'}
    )
    assert response.status_code == 201, response.text
    return response.json()['access_token']


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def jpeg_with_gps(size=(2000, 1000)):
    image = Image.new('RGB', size, 'teal')
    exif = Image.Exif()
    exif[0x8825] = {2: (42.0, 30.0, 0.0)}  # GPSInfo: latitude
    output = BytesIO()
    image.save(output, 'JPEG', exif=exif)
    return output.getvalue()


def upload(client, token, session_id, content, name='photo.jpg', content_type='image/jpeg'):
    return client.post(
        '/chat/images',
        data={'session_id': session_id},
        files={'file': (name, content, content_type)},
        headers=bearer(token) if token else {},
    )


def new_session(client, username):
    token = register(client, username)
    session_id = client.post('/chat/session', headers=bearer(token)).json()['session_id']
    return token, session_id


def chat(client, token, session_id, frames):
    replies = []
    with client.websocket_connect(
        f'/ws/chat/{session_id}', headers={'origin': 'http://localhost:3000'}
    ) as websocket:
        websocket.send_json({'type': 'auth', 'token': token})
        assert websocket.receive_json()['type'] == 'connected'
        for frame in frames:
            websocket.send_json(frame)
            while True:
                event = websocket.receive_json()
                if event['type'] in {'message_end', 'error'}:
                    replies.append(event)
                    break
    return replies


def test_photo_reaches_agent_once_and_is_not_stored(client, monkeypatch):
    token, session_id = new_session(client, 'chat_photo_owner')
    received = []

    async def offline_reply(message, state, history, on_chunk=None, image=None):
        received.append((message, image))
        return 'На фото горное озеро.', state, False

    monkeypatch.setattr(chat_service, 'respond', offline_reply)
    response = upload(client, token, session_id, jpeg_with_gps())
    assert response.status_code == 201, response.text
    image_id = response.json()['image_id']

    first, repeated = chat(
        client,
        token,
        session_id,
        [
            {'type': 'message', 'message': 'Хочу сюда', 'image_id': image_id},
            {'type': 'message', 'message': 'Ещё раз', 'image_id': image_id},
        ],
    )

    assert first['type'] == 'message_end'
    assert repeated == {
        'type': 'error',
        'code': 'image_not_found',
        'message': 'Фото не найдено или устарело. Загрузите его ещё раз.',
    }
    message, image = received[0]
    assert message == 'Хочу сюда\n[фото]'
    with Image.open(BytesIO(image)) as sent:
        assert sent.format == 'WEBP'
        assert sent.size == (1536, 768)
        assert not sent.getexif()
    history = client.get(f'/chat/history/{session_id}', headers=bearer(token)).json()
    assert [item['content'] for item in history[-2:]] == [
        'Хочу сюда\n[фото]',
        'На фото горное озеро.',
    ]
    assert chat_images._pending == {}


def test_photo_without_text_is_accepted(client, monkeypatch):
    token, session_id = new_session(client, 'chat_photo_only')
    received = []

    async def offline_reply(message, state, history, on_chunk=None, image=None):
        received.append(message)
        return 'Красивое место.', state, False

    monkeypatch.setattr(chat_service, 'respond', offline_reply)
    image_id = upload(client, token, session_id, jpeg_with_gps()).json()['image_id']

    (reply,) = chat(client, token, session_id, [{'type': 'message', 'image_id': image_id}])

    assert reply['type'] == 'message_end'
    assert received == ['[фото]']


def test_photo_belongs_to_its_client_and_session(client, monkeypatch):
    token, session_id = new_session(client, 'chat_photo_first')
    other_token, other_session = new_session(client, 'chat_photo_second')

    assert upload(client, None, session_id, jpeg_with_gps()).status_code == 401
    assert upload(client, other_token, session_id, jpeg_with_gps()).status_code == 404
    image_id = upload(client, token, session_id, jpeg_with_gps()).json()['image_id']

    (stolen,) = chat(
        client,
        other_token,
        other_session,
        [{'type': 'message', 'message': 'Чужое фото', 'image_id': image_id}],
    )

    assert stolen['code'] == 'image_not_found'
    assert image_id in chat_images._pending


def test_upload_rejects_files_that_are_not_photos(client):
    token, session_id = new_session(client, 'chat_photo_invalid')

    text = upload(client, token, session_id, b'not an image', 'notes.txt', 'text/plain')
    svg = upload(
        client,
        token,
        session_id,
        b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        'logo.svg',
        'image/svg+xml',
    )

    assert text.status_code == 400
    assert svg.status_code == 400
    assert chat_images._pending == {}


def test_phone_sized_photo_passes_the_request_body_limit(client):
    token, session_id = new_session(client, 'chat_photo_large')
    output = BytesIO()
    Image.frombytes('RGB', (1200, 1000), os.urandom(3_600_000)).save(output, 'PNG')
    assert output.tell() > 1_048_576

    response = upload(client, token, session_id, output.getvalue(), 'photo.png', 'image/png')

    assert response.status_code == 201, response.text


def test_waiting_photos_are_limited_per_client(client):
    token, session_id = new_session(client, 'chat_photo_queue')

    statuses = [
        upload(client, token, session_id, jpeg_with_gps((64, 48))).status_code for _ in range(4)
    ]

    assert statuses == [201, 201, 201, 429]
