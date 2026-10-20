def test_country_and_region_round_trip(client, admin_headers):
    country_response = client.post(
        "/countries/",
        json={"name": "Кыргызстан"},
        headers=admin_headers,
    )
    assert country_response.status_code == 200, country_response.text

    country_id = country_response.json()["id"]
    region_response = client.post(
        "/regions/",
        json={"name": "Чүй", "country_id": country_id},
        headers=admin_headers,
    )
    assert region_response.status_code == 200, region_response.text
    assert region_response.json()["country_id"] == country_id

    list_response = client.get("/regions/")
    assert list_response.status_code == 200
    assert {
        "id": region_response.json()["id"],
        "name": "Чүй",
        "image": None,
        "country_id": country_id,
    } in list_response.json()
