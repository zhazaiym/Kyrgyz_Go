from fastapi.testclient import TestClient

from main import app


def test_admin_paths_require_login_but_are_available_from_any_ip():
    with TestClient(app, client=('198.51.100.40', 50000)) as remote:
        assert remote.get('/admin/', follow_redirects=False).status_code in (302, 303)
        assert remote.get('/').status_code == 200
