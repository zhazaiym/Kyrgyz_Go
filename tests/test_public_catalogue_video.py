from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import event

from mysite.api import video_media
from mysite.database import models as m
from mysite.database.db import SessionLocal, engine
from tests.test_shared_client_access import catalogue_entries  # noqa: F401


@pytest.mark.parametrize(
    'path,model,parent,key',
    [
        ('tour-images', m.TourImage, m.Tour, 'tour_id'),
        ('tour-programs', m.TourProgram, m.Tour, 'tour_id'),
        ('hotel-images', m.HotelImage, m.Hotel, 'hotel_id'),
        ('transport-images', m.TransportImage, m.Transport, 'transport_id'),
        ('trekking-images', m.TrekkingImage, m.Trekking, 'trekking_id'),
        ('trekking-programs', m.TrekkingProgram, m.Trekking, 'trekking_id'),
        ('helicopter-images', m.HelicopterImage, m.HelicopterTour, 'helicopter_id'),
        ('tour-videos', m.TourVideo, m.Tour, 'tour_id'),
    ],
)
def test_nested_resources_hide_inactive_and_missing_parents(
    client, request, path, model, parent, key
):
    paths = {
        m.Tour: '/tours/',
        m.Hotel: '/hotels/',
        m.Transport: '/transports/',
        m.Trekking: '/trekkings/',
        m.HelicopterTour: '/helicopter-tours/',
    }
    identity = dict(request.getfixturevalue('catalogue_entries'))[paths[parent]]
    values = {key: identity}
    if 'image' in model.__table__.c:
        values['image'] = '/media/test.webp'
    elif model is m.TourVideo:
        values['video_url'] = '/media/test.mp4'
    else:
        values['day_number'] = 1
    with SessionLocal() as db:
        child = model(**values)
        db.add(child)
        db.commit()
        child_id = child.id
    assert client.get(f'/{path}/{child_id}/').status_code == 200
    assert client.get(f'/{path}/', params={key: identity}).status_code == 200
    with SessionLocal() as db:
        db.get(parent, identity).is_active = False
        db.commit()
    assert client.get(f'{paths[parent]}{identity}/').status_code == 404
    assert client.get(f'{paths[parent]}2147483647/').status_code == 404
    assert client.get(f'/{path}/{child_id}/').status_code == 404
    assert client.get(f'/{path}/2147483647/').status_code == 404
    for parent_id in (identity, 2147483647):
        assert client.get(f'/{path}/', params={key: parent_id}).status_code == 404
    assert child_id not in [item['id'] for item in client.get(f'/{path}/').json()]


def upload(client, headers, content, filename='untrusted.bin', mime='application/octet-stream'):
    return client.post(
        '/admin/media/videos/', headers=headers, files={'file': (filename, content, mime)}
    )


@pytest.mark.parametrize('extension,mime', [('mp4', 'video/mp4'), ('webm', 'video/webm')])
def test_real_video_upload_attach_read_update_delete(client, admin_headers, extension, mime):
    content = (Path(__file__).parent / 'fixtures' / f'video.{extension}').read_bytes()
    response = upload(client, admin_headers, content, '../../wrong.exe', 'text/plain')
    assert response.status_code == 201, response.text
    stored = response.json()
    assert stored['content_type'] == mime and stored['size'] == len(content)
    assert stored['url'].endswith('.' + extension)
    served = client.get(stored['url'])
    assert served.status_code == 200 and served.content == content
    assert served.headers['content-type'] == mime
    partial = client.get(stored['url'], headers={'Range': 'bytes=0-31'})
    assert partial.status_code == 206
    assert partial.content == content[:32]
    assert partial.headers['content-range'] == f'bytes 0-31/{len(content)}'
    tour = client.post(
        '/tours/', headers=admin_headers, json={'title': 'Video example', 'price': 100}
    ).json()
    tour_id = tour['id']
    assert client.get(f'/tours/{tour_id}/').json()['videos'] == []
    attached = client.post(
        '/tour-videos/',
        headers=admin_headers,
        json={'tour_id': tour_id, 'video_url': stored['url'], 'order': 2},
    )
    assert attached.status_code == 200, attached.text
    video_id = attached.json()['id']
    second = client.post(
        '/tour-videos/',
        headers=admin_headers,
        json={'tour_id': tour_id, 'video_url': stored['url'], 'order': 1},
    ).json()
    detail = client.get(f'/tours/{tour_id}/').json()
    assert [row['id'] for row in detail['videos']] == [second['id'], video_id]
    assert 'images' in detail and 'main_image' in detail
    assert (
        client.put(
            f'/tour-videos/{video_id}/',
            headers=admin_headers,
            json={'order': 0, 'poster_url': '/media/poster.webp'},
        ).status_code
        == 200
    )
    assert client.delete(f'/tour-videos/{video_id}/', headers=admin_headers).status_code == 200
    assert client.get(f'/tour-videos/{video_id}/').status_code == 404


def test_video_rejections_cleanup_and_permissions(
    client, admin_headers, customer_headers, monkeypatch, tmp_path
):
    monkeypatch.setattr(video_media, 'MEDIA_ROOT', tmp_path)
    for headers in ({}, customer_headers):
        assert upload(client, headers, b'data').status_code == 401
        for method, path in [
            ('post', '/tour-videos/'),
            ('put', '/tour-videos/1/'),
            ('delete', '/tour-videos/1/'),
        ]:
            assert client.request(method, path, headers=headers, json={}).status_code == 401
    for content in (b'not a video', b'\x00\x00\x00\x18ftypisom' + b'\0' * 500):
        assert upload(client, admin_headers, content, 'fake.mp4', 'video/mp4').status_code == 400
    assert not list(tmp_path.rglob('*.upload'))
    monkeypatch.setenv('MAX_VIDEO_UPLOAD_BYTES', '100')
    from mysite.api.resource_limits import setting

    setting.cache_clear()
    assert upload(client, admin_headers, b'x' * 101).status_code == 413
    assert upload(client, admin_headers, b'x' * 66000).status_code == 413
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


def test_video_detail_query_count_is_constant(client):
    counts = []
    for size in (1, 25):
        with SessionLocal() as db:
            tour = m.Tour(title='Video queries', price=100)
            tour.videos = [m.TourVideo(video_url='/media/test.mp4', order=i) for i in range(size)]
            db.add(tour)
            db.commit()
            identity = tour.id
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(engine, 'before_cursor_execute', record)
        try:
            response = client.get(f'/tours/{identity}/')
            assert response.status_code == 200 and len(response.json()['videos']) == size
        finally:
            event.remove(engine, 'before_cursor_execute', record)
        counts.append(len(statements))
    assert counts[0] == counts[1] == 5


def test_store_video_reads_bounded_chunks_and_removes_partial_file(monkeypatch, tmp_path):
    monkeypatch.setattr(video_media, 'MEDIA_ROOT', tmp_path)

    class BrokenStream(BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 1_048_576
            if self.tell():
                raise OSError('Upload interrupted')
            return super().read(size)

    with pytest.raises(OSError):
        video_media.store_video(BrokenStream(b'x' * 1_048_577))
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


def test_video_roles_and_sqladmin_management(client, admin_headers):
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from main import app
    from mysite.api.admin import password_hash

    content = (Path(__file__).parent / 'fixtures' / 'video.mp4').read_bytes()
    for role in ('manager', 'catalog_editor'):
        username = 'video_' + uuid4().hex[:16]
        password = 'VideoRolePassword123!'
        with SessionLocal() as db:
            db.add(
                m.Admin(username=username, hashed_password=password_hash.hash(password), role=role)
            )
            db.commit()
        tokens = client.post('/admin/login/', json={'username': username, 'password': password})
        assert tokens.status_code == 200
        headers = {'Authorization': 'Bearer ' + tokens.json()['access_token']}
        response = upload(client, headers, content)
        assert response.status_code == (201 if role == 'catalog_editor' else 401)
        with TestClient(app) as browser:
            assert (
                browser.post(
                    '/admin/media/video-upload', files={'file': ('clip.mp4', content)}
                ).status_code
                == 401
            )
            login = browser.post(
                '/admin/login',
                data={'username': username, 'password': password},
                follow_redirects=False,
            )
            assert login.status_code in (302, 303)
            page = browser.get('/admin/tour-video/create', follow_redirects=False)
            assert page.status_code == (200 if role == 'catalog_editor' else 403)
            result = browser.post(
                '/admin/media/video-upload', files={'file': ('clip.mp4', content)}
            )
            assert result.status_code == (201 if role == 'catalog_editor' else 401)


def test_video_upload_unknown_length_request_is_bounded(client, admin_headers, monkeypatch):
    from mysite.api.resource_limits import setting

    monkeypatch.setenv('MAX_VIDEO_UPLOAD_BYTES', '100')
    setting.cache_clear()
    boundary = b'video-test'

    def chunks():
        yield (
            b'--'
            + boundary
            + b'\r\nContent-Disposition: form-data; name="file"; filename="clip.mp4"\r\n\r\n'
        )
        for _ in range(70):
            yield b'x' * 1024
        yield b'\r\n--' + boundary + b'--\r\n'

    response = client.post(
        '/admin/media/videos/',
        headers={**admin_headers, 'Content-Type': 'multipart/form-data; boundary=video-test'},
        content=chunks(),
    )
    assert response.status_code == 413
