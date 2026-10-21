def test_catalogue_read_is_public(client):
    response = client.get("/tour-categories/")
    assert response.status_code == 200


def test_catalogue_write_requires_admin(client):
    response = client.post("/tour-categories/", json={"name": "Protected"})
    assert response.status_code == 401


def test_admin_can_write_catalogue(client, admin_headers):
    response = client.post(
        "/tour-categories/",
        json={"name": "Authorized"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text


def test_contact_listing_is_public_and_detail_remains_private(client):
    response = client.post("/contacts/", json={"phone": "+996700000000"})
    assert response.status_code == 200, response.text
    assert client.get("/contacts/").status_code == 200
    assert client.get(f"/contacts/{response.json()['id']}/").status_code == 401


def test_travel_request_submission_is_public_but_listing_is_private(client):
    response = client.post(
        "/travel-requests/",
        json={"name": "Frontend User", "phone": "+996700000001"},
    )
    assert response.status_code == 200, response.text
    assert client.get("/travel-requests/").status_code == 401


def test_admin_can_list_travel_requests(client, admin_headers):
    response = client.get("/travel-requests/", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert any(item["phone"] == "+996700000001" for item in response.json())


def test_sqladmin_requires_login(client):
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert response.headers["location"].endswith("/admin/login")


def test_sqladmin_accepts_existing_admin_credentials(client, admin_headers):
    del admin_headers
    response = client.post(
        "/admin/login",
        data={"username": "test-admin", "password": "StrongAdminPassword123!"},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}
    assert client.get("/admin/").status_code == 200
    client.get("/admin/logout")
