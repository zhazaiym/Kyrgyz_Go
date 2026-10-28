from fastapi.testclient import TestClient

from main import app


def test_admin_paths_are_restricted_to_configured_networks():
    with TestClient(app, client=('198.51.100.40', 50000)) as untrusted:
        assert untrusted.get('/admin/me/').status_code == 403
        assert untrusted.post('/admin/login/').status_code == 403
        assert untrusted.get('/').status_code == 200

    with TestClient(app, client=('127.0.0.1', 50000)) as allowed:
        assert allowed.get('/admin/me/').status_code == 401
