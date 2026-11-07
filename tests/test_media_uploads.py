import os
import subprocess
import sys
from io import BytesIO
from urllib.parse import urlsplit

from PIL import Image


def image_bytes(image_format='PNG', size=(64, 48), mode='RGB', color='teal'):
    output = BytesIO()
    Image.new(mode, size, color).save(output, image_format)
    return output.getvalue()


def upload(client, headers, content, name='photo.png', content_type='image/png'):
    return client.post(
        '/admin/media/', files={'file': (name, content, content_type)}, headers=headers
    )


def test_uploaded_image_reaches_frontend_as_url(client, admin_headers):
    response = upload(client, admin_headers, image_bytes())

    assert response.status_code == 201, response.text
    url = response.json()['url']
    assert url.startswith('/media/')
    assert url.endswith('.webp')

    served = client.get(urlsplit(url).path)
    assert served.status_code == 200
    assert served.headers['content-type'] == 'image/webp'
    assert Image.open(BytesIO(served.content)).size == (64, 48)

    transport = client.post(
        '/transports/',
        json={'name': 'Toyota RAV4', 'seats': 5, 'price': '140.00', 'main_image': url},
        headers=admin_headers,
    )
    assert transport.status_code == 200, transport.text
    listed = client.get('/transports/').json()
    assert any(item['main_image'] == url for item in listed)


def test_upload_requires_admin_token(client, customer_headers):
    assert upload(client, {}, image_bytes()).status_code == 401
    assert upload(client, customer_headers, image_bytes()).status_code == 401


def test_upload_rejects_files_that_are_not_images(client, admin_headers):
    text = upload(client, admin_headers, b'not an image', 'notes.txt', 'text/plain')
    svg = upload(
        client,
        admin_headers,
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        'logo.svg',
        'image/svg+xml',
    )
    gif = upload(client, admin_headers, image_bytes('GIF'), 'photo.gif', 'image/gif')

    assert text.status_code == 400
    assert svg.status_code == 400
    assert gif.status_code == 400


def test_upload_rejects_images_over_the_size_limit(client, admin_headers, monkeypatch):
    from mysite.api.resource_limits import setting

    monkeypatch.setenv('MAX_IMAGE_UPLOAD_BYTES', '1024')
    setting.cache_clear()

    response = upload(client, admin_headers, image_bytes('BMP', (200, 200)), 'big.png')

    assert response.status_code == 413


def test_large_images_are_resized_and_transparency_is_kept(client, admin_headers):
    response = upload(
        client, admin_headers, image_bytes('PNG', (3000, 1500), 'RGBA', (0, 128, 128, 120))
    )

    assert response.status_code == 201, response.text
    served = client.get(urlsplit(response.json()['url']).path)
    image = Image.open(BytesIO(served.content))
    assert image.size == (2560, 1280)
    assert image.mode == 'RGBA'


def test_admin_panel_uploads_with_session_and_shows_picker(client, admin_headers):
    files = {'file': ('photo.jpg', image_bytes('JPEG'), 'image/jpeg')}
    client.get('/admin/logout')
    assert client.post('/admin/media/upload', files=files).status_code == 401

    login = client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    response = client.post('/admin/media/upload', files=files)
    assert response.status_code == 201, response.text
    assert '/media/' in response.json()['url']

    form = client.get('/admin/transport/create')
    assert form.status_code == 200
    assert '/admin/media/upload' in form.text


def test_webp_content_type_does_not_depend_on_system_mime_types():
    code = (
        'import mimetypes; mimetypes.knownfiles = []; mimetypes.init(); '
        'import mysite.api.media; '
        "print(mimetypes.guess_type('photo.webp')[0])"
    )
    result = subprocess.run(
        [sys.executable, '-B', '-c', code],
        cwd=os.getcwd(),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'image/webp'
