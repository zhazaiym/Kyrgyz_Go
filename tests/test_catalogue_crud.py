def create(client, path, payload, headers):
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 200, f"POST {path}: {response.text}"
    return response.json()


def fake_translations(data):
    return {
        language: {
            "title": f"{data['title']} {language}",
            "description": data["description"],
            "included": data["included"],
            "excluded": data["excluded"],
        }
        for language in ("en", "de", "zh")
    }


def test_location_hotel_and_tour_creation(client, admin_headers, customer_headers, monkeypatch):
    monkeypatch.setattr("mysite.api.tour.translate_tour", fake_translations)

    category = create(client, "/tour-categories/", {"name": "Adventure"}, admin_headers)
    country = create(client, "/countries/", {"name": "Kyrgyzstan"}, admin_headers)
    region = create(client, "/regions/", {
        "name": "Naryn", "country_id": country["id"]
    }, admin_headers)
    district = create(client, "/districts/", {
        "name": "At-Bashy", "region_id": region["id"]
    }, admin_headers)
    hotel = create(client, "/hotels/", {
        "region_id": region["id"], "district_id": district["id"],
        "name": "Test Hotel", "price": "100.00"
    }, admin_headers)
    create(client, "/hotel-images/", {
        "hotel_id": hotel["id"], "image": "https://example.com/hotel.jpg"
    }, admin_headers)

    tour = create(client, "/tours/", {
        "category_id": category["id"], "title": "Test Tour",
        "description": "Test description", "price": "250.00"
    }, admin_headers)
    create(client, "/tour-images/", {
        "tour_id": tour["id"], "image": "https://example.com/tour.jpg"
    }, admin_headers)
    create(client, "/tour-programs/", {
        "tour_id": tour["id"], "day_number": 1, "title": "Arrival"
    }, admin_headers)

    detail = client.get(f"/tours/{tour['id']}/?lang=en", headers=customer_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["title"] == "Test Tour en"
    assert len(detail.json()["images"]) == 1
    assert len(detail.json()["programs"]) == 1


def test_transport_helicopter_and_trekking_creation(client, admin_headers, customer_headers):
    transport = create(client, "/transports/", {
        "name": "Test Van", "seats": 8, "price": "80.00"
    }, admin_headers)
    create(client, "/transport-images/", {
        "transport_id": transport["id"], "image": "https://example.com/van.jpg"
    }, admin_headers)

    helicopter = create(client, "/helicopter-tours/", {
        "title": "Test Flight", "price": "900.00"
    }, admin_headers)
    create(client, "/helicopter-images/", {
        "helicopter_id": helicopter["id"], "image": "https://example.com/flight.jpg"
    }, admin_headers)

    trekking = create(client, "/trekkings/", {
        "title": "Test Trek", "price": "120.00"
    }, admin_headers)
    create(client, "/trekking-images/", {
        "trekking_id": trekking["id"], "image": "https://example.com/trek.jpg"
    }, admin_headers)
    create(client, "/trekking-programs/", {
        "trekking_id": trekking["id"], "day_number": 1, "title": "Start"
    }, admin_headers)

    assert client.get(f"/transports/{transport['id']}/", headers=customer_headers).status_code == 200
    assert client.get(f"/helicopter-tours/{helicopter['id']}/", headers=customer_headers).status_code == 200
    assert client.get(f"/trekkings/{trekking['id']}/", headers=customer_headers).status_code == 200


def test_content_records_can_be_managed_by_admin(client, admin_headers):
    about = create(client, "/abouts/", {"title": "About"}, admin_headers)
    section = create(client, "/about-sections/", {"title": "Section"}, admin_headers)
    faq = create(client, "/faqs/", {
        "question": "Question?", "answer": "Answer."
    }, admin_headers)
    contact = create(client, "/contacts/", {
        "phone": "+996700000003", "city": "Bishkek"
    }, admin_headers)

    assert client.put(
        f"/abouts/{about['id']}/", json={"title": "Updated"}, headers=admin_headers
    ).status_code == 200
    assert client.get(f"/about-sections/{section['id']}/").status_code == 200
    assert client.get(f"/faqs/{faq['id']}/").status_code == 200
    assert client.get(
        f"/contacts/{contact['id']}/", headers=admin_headers
    ).status_code == 200
