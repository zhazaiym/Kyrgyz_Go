import pytest

from mysite.api.origin_config import validate_origin_settings


@pytest.mark.parametrize(
    'origins',
    [
        'https://kerben.vercel.app',
        'https://kerben.kg;http://localhost:3000;http://127.0.0.1:3000',
        'http://[::1]:3000',
    ],
)
def test_https_sites_and_loopback_are_trusted(monkeypatch, origins):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', origins)
    monkeypatch.setenv('CHAT_ALLOWED_ORIGINS', origins)
    validate_origin_settings()


@pytest.mark.parametrize(
    'origin',
    [
        '*',
        'http://kerben.example',
        'https://*.vercel.app',
        'https://kerben.vercel.app/ru',
        'https://user@kerben.vercel.app',
        'kerben.vercel.app',
    ],
)
@pytest.mark.parametrize('variable', ['CORS_ALLOWED_ORIGINS', 'CHAT_ALLOWED_ORIGINS'])
def test_untrusted_origin_stops_the_launch(monkeypatch, variable, origin):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', 'https://kerben.vercel.app')
    monkeypatch.setenv('CHAT_ALLOWED_ORIGINS', 'https://kerben.vercel.app')
    monkeypatch.setenv(variable, f'https://kerben.vercel.app;{origin}')
    with pytest.raises(RuntimeError, match=variable):
        validate_origin_settings()


def test_admin_form_from_the_client_site_is_refused(client):
    response = client.post(
        '/admin/login',
        data={'username': 'nobody', 'password': 'nothing'},
        headers={'Origin': 'http://localhost:3000', 'Cookie': 'session=x'},
    )
    assert response.status_code == 403
