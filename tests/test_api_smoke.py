import pytest


PUBLIC_LIST_ROUTES = [
    "/",
    "/openapi.json",
    "/tour-categories/",
    "/tours/",
    "/countries/",
    "/regions/",
    "/districts/",
    "/hotels/",
    "/hotel-images/",
    "/transports/",
    "/transport-images/",
    "/helicopter-tours/",
    "/helicopter-images/",
    "/trekkings/",
    "/trekking-images/",
    "/trekking-programs/",
    "/faqs/",
    "/abouts/",
    "/about-sections/",
    "/tour-images/",
    "/tour-programs/",
]


@pytest.mark.parametrize("path", PUBLIC_LIST_ROUTES)
def test_public_read_routes_respond(client, path):
    response = client.get(path)
    assert response.status_code == 200, f"{path}: {response.text}"


PROTECTED_WRITES = [
    ("post", "/abouts/"), ("put", "/abouts/1/"), ("delete", "/abouts/1/"),
    ("post", "/about-sections/"), ("put", "/about-sections/1/"), ("delete", "/about-sections/1/"),
    ("post", "/tour-categories/"), ("put", "/tour-categories/1/"), ("delete", "/tour-categories/1/"),
    ("post", "/tours/"), ("put", "/tours/1/"), ("delete", "/tours/1/"),
    ("post", "/tours/1/translate/"),
    ("post", "/countries/"), ("put", "/countries/1/"), ("delete", "/countries/1/"),
    ("post", "/regions/"), ("put", "/regions/1/"), ("delete", "/regions/1/"),
    ("post", "/districts/"), ("put", "/districts/1/"), ("delete", "/districts/1/"),
    ("post", "/hotels/"), ("put", "/hotels/1/"), ("delete", "/hotels/1/"),
    ("post", "/hotel-images/"), ("put", "/hotel-images/1/"), ("delete", "/hotel-images/1/"),
    ("post", "/transports/"), ("put", "/transports/1/"), ("delete", "/transports/1/"),
    ("post", "/transport-images/"), ("put", "/transport-images/1/"), ("delete", "/transport-images/1/"),
    ("post", "/helicopter-tours/"), ("put", "/helicopter-tours/1/"), ("delete", "/helicopter-tours/1/"),
    ("post", "/helicopter-images/"), ("put", "/helicopter-images/1/"), ("delete", "/helicopter-images/1/"),
    ("post", "/trekkings/"), ("put", "/trekkings/1/"), ("delete", "/trekkings/1/"),
    ("post", "/trekking-images/"), ("put", "/trekking-images/1/"), ("delete", "/trekking-images/1/"),
    ("post", "/trekking-programs/"), ("put", "/trekking-programs/1/"), ("delete", "/trekking-programs/1/"),
    ("post", "/faqs/"), ("put", "/faqs/1/"), ("delete", "/faqs/1/"),
    ("put", "/contacts/1/"), ("delete", "/contacts/1/"),
    ("post", "/tour-images/"), ("put", "/tour-images/1/"), ("delete", "/tour-images/1/"),
    ("post", "/tour-programs/"), ("put", "/tour-programs/1/"), ("delete", "/tour-programs/1/"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_WRITES)
def test_catalogue_writes_reject_anonymous_requests(client, method, path):
    response = client.request(method.upper(), path, json={})
    assert response.status_code == 401, f"{method.upper()} {path}: {response.text}"


def test_private_customer_routes_reject_anonymous_requests(client):
    assert client.get("/contacts/").status_code == 401
    assert client.get("/contacts/1/").status_code == 401
    assert client.get("/travel-requests/").status_code == 401
    assert client.get("/travel-requests/1/").status_code == 401
    assert client.put("/travel-requests/1/", json={}).status_code == 401
    assert client.delete("/travel-requests/1/").status_code == 401


def test_openapi_contains_legacy_booking_route(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/bookings/" in paths


def test_legacy_booking_submission_creates_request(
    client, admin_headers, monkeypatch
):
    monkeypatch.setattr("mysite.api.tour.try_save_translations", lambda *args: None)
    category = client.post(
        "/tour-categories/",
        json={"name": "Booking category"},
        headers=admin_headers,
    ).json()
    tour = client.post(
        "/tours/",
        json={
            "category_id": category["id"],
            "title": "Bookable tour",
            "price": "50.00",
        },
        headers=admin_headers,
    ).json()

    response = client.post(
        "/bookings/",
        json={
            "tour_id": tour["id"],
            "name": "Booking User",
            "phone": "+996700000099",
            "travelers_count": 2,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["booking_id"] > 0
    assert response.json()["status"] == "new"
