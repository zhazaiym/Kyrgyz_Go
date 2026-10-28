from uuid import uuid4

from sqlalchemy import event

from mysite.database import models as m
from mysite.database.chat_models import ChatBookingLink, ChatSession
from mysite.database.db import SessionLocal, engine
from mysite.database.selection_models import TravelSelection
from tests.test_main_regressions import headers, register


def count_selects(client, path, auth):
    queries = []

    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)

    event.listen(engine, 'before_cursor_execute', record)
    try:
        response = client.get(path, headers=auth)
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    return len(queries), response.json()


def test_catalogue_and_selection_queries_stay_constant_as_page_grows(client, admin_headers):
    account, _ = register(client)
    marker = 'QueryScale' + uuid4().hex[:10]
    samples = {}
    with SessionLocal() as db:
        region = m.Region(name=marker)
        district = m.District(name=marker, region=region)
        db.add_all([region, district])
        db.commit()
        region_id, district_id = region.id, district.id
    for size in (1, 20):
        with SessionLocal() as db:
            for index in range(0 if size == 1 else 1, size):
                tour = m.Tour(title=f'{marker} {index}', price=10)
                hotel = m.Hotel(
                    name=f'{marker} {index}', price=10, region_id=region_id, district_id=district_id
                )
                transport = m.Transport(name=f'{marker} {index}', price=10, seats=4)
                session = ChatSession(id=str(uuid4()), client_id=account['client_id'], state={})
                request = m.TravelRequest(name='Query Guest', phone='+996700123456')
                db.add_all([tour, hotel, transport, session, request])
                db.flush()
                db.add(m.TourTranslation(tour_id=tour.id, lang='en', title=f'{marker} {index}'))
                db.add(
                    TravelSelection(
                        client_id=account['client_id'],
                        tour_id=tour.id,
                        hotel_id=hotel.id,
                        transport_id=transport.id,
                        session_id=session.id,
                    )
                )
                db.add(
                    ChatBookingLink(
                        client_id=account['client_id'],
                        session_id=session.id,
                        request_id=request.id,
                        revision=0,
                    )
                )
            db.commit()
        for path, auth in [
            (f'/tours/?lang=en&search={marker}', headers(account)),
            ('/travel-selections/me/', headers(account)),
            ('/manager/travel-selections/', admin_headers),
        ]:
            number, _ = count_selects(client, path, auth)
            samples[size, path] = number
            assert number <= (2 if path.startswith('/tours/') else 8), (path, number)
    for (size, path), number in samples.items():
        if size == 20:
            assert number <= samples[1, path] + 1, 'A query per row has been reintroduced'


def test_list_limits_are_applied_and_clients_can_page(client):
    marker = 'BoundedPage' + uuid4().hex[:10]
    with SessionLocal() as db:
        db.add_all(m.Tour(title=f'{marker} {index:03}', price=10) for index in range(111))
        db.commit()
    first = client.get('/tours/', params={'search': marker}).json()
    assert len(first) == 100
    next_page = client.get('/tours/', params={'search': marker, 'offset': 100}).json()
    assert len(next_page) == 11
    assert not {row['id'] for row in first} & {row['id'] for row in next_page}
    assert client.get('/tours/', params={'limit': 101}).status_code == 422


def test_detail_queries_do_not_grow_with_program_size(client, customer_headers):
    with SessionLocal() as db:
        tour = m.Tour(title='Detail query audit', price=10)
        db.add(tour)
        db.flush()
        identity = tour.id
        db.add(m.TourProgram(tour_id=identity, day_number=1, title='Day 1'))
        db.commit()
    first, _ = count_selects(client, f'/tours/{identity}/?lang=en', customer_headers)
    with SessionLocal() as db:
        db.add_all(
            m.TourProgram(tour_id=identity, day_number=index, title=f'Day {index}')
            for index in range(2, 22)
        )
        db.commit()
    second, payload = count_selects(client, f'/tours/{identity}/?lang=en', customer_headers)
    assert len(payload['programs']) == 21
    assert second == first <= 6
