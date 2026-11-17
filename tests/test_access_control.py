def test_catalogue_read_is_public(client):
    response = client.get('/tour-categories/')
    assert response.status_code == 200


def test_contact_listing_is_public(client, seed):
    from mysite.database.models import Contact

    identity = seed(Contact, phone='+996700000000')
    assert client.get('/contacts/').status_code == 200
    assert client.get(f'/contacts/{identity}/').status_code == 200


def test_travel_request_submission_requires_client_and_listing_is_private(client):
    response = client.post(
        '/travel-requests/',
        json={
            'selection_id': 1,
            'travel_date': '2099-01-01',
            'travelers_count': 1,
            'phone': '+996700000001',
        },
    )
    assert response.status_code == 401, response.text
    assert client.get('/travel-requests/').status_code == 405


def test_sqladmin_requires_login(client):
    response = client.get('/admin/', follow_redirects=False)
    assert response.status_code in {302, 303}
    assert response.headers['location'].endswith('/admin/login')


def test_sqladmin_accepts_existing_admin_credentials(client, panel_admin):
    response = client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert client.get('/admin/').status_code == 200
    client.get('/admin/logout')
