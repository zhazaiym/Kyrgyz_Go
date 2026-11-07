def test_authenticated_admin_receives_new_request_event(client, admin_headers):
    from mysite.admin.realtime import publish_new_request

    login = client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    with client.websocket_connect('/admin/ws/requests') as websocket:
        publish_new_request(713)
        assert websocket.receive_json() == {'type': 'new_request', 'request_id': 713}


def test_admin_request_list_includes_live_update_script(client, admin_headers):
    client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )

    response = client.get('/admin/travel-request/list')

    assert response.status_code == 200
    assert '/admin/ws/requests' in response.text
    assert 'new_request' in response.text
