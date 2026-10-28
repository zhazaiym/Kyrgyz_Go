from decimal import Decimal

import pytest

from mysite.database import models
from mysite.database.db import SessionLocal


def test_helicopter_fields_are_returned(client, admin_headers, customer_headers):
    fields = dict(
        duration_minutes=45,
        max_passengers=4,
        departure_location='Bishkek',
        destination='Ala-Archa',
        main_image='https://example.com/helicopter.jpg',
    )
    response = client.post(
        '/helicopter-tours/',
        headers=admin_headers,
        json=dict(title='Contract flight', price='1000', **fields),
    )
    assert response.status_code == 200, response.text
    flight = response.json()
    for path in ['/helicopter-tours/', f'/helicopter-tours/{flight["id"]}/']:
        data = client.get(path, headers=customer_headers).json()
        item = next(x for x in data if x['id'] == flight['id']) if isinstance(data, list) else data
        assert {key: item.get(key) for key in fields} == fields


def test_tour_coordinates_round_trip_and_validation(
    client, admin_headers, customer_headers, monkeypatch
):
    monkeypatch.setattr(
        'mysite.api.tour.translate_tour', lambda data: {lang: data for lang in ('en', 'de', 'zh')}
    )
    response = client.post(
        '/tours/',
        headers=admin_headers,
        json={'title': 'Map tour', 'price': '100', 'latitude': 42.64, 'longitude': 74.48},
    )
    assert response.status_code == 200, response.text
    tour = response.json()
    detail = client.get(f'/tours/{tour["id"]}/', headers=customer_headers).json()
    assert Decimal(str(detail.get('latitude'))) == Decimal('42.64')
    assert Decimal(str(detail.get('longitude'))) == Decimal('74.48')
    response = client.put(f'/tours/{tour["id"]}/', headers=admin_headers, json={'latitude': -91})
    assert response.status_code == 422
    response = client.put(
        f'/tours/{tour["id"]}/', headers=admin_headers, json={'latitude': None, 'longitude': None}
    )
    assert response.status_code == 200
    assert response.json()['latitude'] is None


def test_tour_category_returns_cards_and_home_slides_return_descriptions(
    client, admin_headers, customer_headers, monkeypatch
):
    monkeypatch.setattr(
        'mysite.api.tour.translate_tour',
        lambda data: {
            lang: dict(
                data, title=f'{data["title"]} {lang}', description=f'{data["description"]} {lang}'
            )
            for lang in ('en', 'de', 'zh')
        },
    )
    category = client.post(
        '/tour-categories/', json={'name': 'Visible category'}, headers=admin_headers
    ).json()
    tour = client.post(
        '/tours/',
        headers=admin_headers,
        json={
            'category_id': category['id'],
            'title': 'Visible tour',
            'description': 'Description',
            'price': '10',
            'main_image': 'https://example.com/tour.jpg',
        },
    ).json()

    by_category = client.get(f'/tours/category/{category["id"]}/?lang=en')
    assert by_category.status_code == 200, by_category.text
    assert by_category.json()[0]['title'] == 'Visible tour en'
    assert not {'description', 'included', 'excluded'} & by_category.json()[0].keys()
    detail = client.get(f'/tours/{tour["id"]}/?lang=en', headers=customer_headers)
    assert detail.status_code == 200 and detail.json()['description'] == 'Description en'

    slides = client.get('/tours/home/slides/?lang=en')
    assert slides.status_code == 200, slides.text
    slide = next(item for item in slides.json()['slides'] if item['id'] == tour['id'])
    assert slide['description'] == 'Description en'


@pytest.mark.parametrize(
    'model,path,field,payload',
    [
        (models.Hotel, '/hotels/', 'name', {}),
        (models.FAQ, '/faqs/', 'question', {'answer': 'Answer'}),
        (models.Transport, '/transports/', 'name', {'seats': 4}),
        (models.Trekking, '/trekkings/', 'title', {}),
        (models.HelicopterTour, '/helicopter-tours/', 'title', {}),
        (models.About, '/abouts/', 'title', {}),
        (models.AboutSection, '/about-sections/', 'title', {}),
        (models.TourCategory, '/tour-categories/', 'name', {}),
        (models.Country, '/countries/', 'name', {}),
        (models.Region, '/regions/', 'name', {}),
        (models.District, '/districts/', 'name', {}),
        (models.Contact, '/contacts/', 'city', {}),
        (models.TourProgram, '/tour-programs/', 'title', {'day_number': 1}),
        (models.TrekkingProgram, '/trekking-programs/', 'title', {'day_number': 1}),
    ],
)
def test_language_on_list_and_detail(client, customer_headers, model, path, field, payload):
    with SessionLocal() as db:
        country = models.Country(name='Language country')
        region = models.Region(name='Language region', country=country)
        district = models.District(name='Language district', region=region)
        tour = models.Tour(title='Parent tour', price=10)
        trek = models.Trekking(title='Parent trek', price=10)
        db.add_all([country, region, district, tour, trek])
        db.flush()
        if model is models.Hotel:
            payload = dict(payload, region_id=region.id, district_id=district.id)
        elif model is models.District:
            payload = dict(payload, region_id=region.id)
        elif model is models.TourProgram:
            payload = dict(payload, tour_id=tour.id)
        elif model is models.TrekkingProgram:
            payload = dict(payload, trekking_id=trek.id)
        if 'price' in model.__table__.columns:
            payload = dict(payload, price=10)
        record = model(**payload, **{field: 'Original'})
        from mysite.translations.content import mark_manual_translations

        record.translations = mark_manual_translations(
            {'en': {field: 'English'}, 'de': {field: 'Deutsch'}, 'zh': {field: 'Chinese'}},
            {field: 'Original'},
        )
        db.add(record)
        db.commit()
        record_id = record.id
    for lang, expected in [
        ('ru', 'Original'),
        ('en', 'English'),
        ('de', 'Deutsch'),
        ('zh', 'Chinese'),
    ]:
        headers = customer_headers if model in (models.TourProgram, models.TrekkingProgram) else {}
        response = client.get(path, params={'lang': lang}, headers=headers)
        assert response.status_code == 200, response.text
        assert next(x for x in response.json() if x['id'] == record_id)[field] == expected
        # Only the requested contacts list becomes public.
        if model is not models.Contact:
            response = client.get(
                f'{path}{record_id}/', params={'lang': lang}, headers=customer_headers
            )
            assert response.status_code == 200, response.text
            assert response.json()[field] == expected
    assert client.get(path, params={'lang': 'invalid'}, headers=customer_headers).status_code == 422


def test_translation_does_not_replace_non_text_fields(client, customer_headers):
    with SessionLocal() as db:
        record = models.Trekking(title='Original', price=10)
        record.translations = {'en': {'title': 'English', 'price': '999', 'id': 999}}
        db.add(record)
        db.commit()
        record_id = record.id
    data = client.get(f'/trekkings/{record_id}/?lang=en', headers=customer_headers).json()
    assert data['id'] == record_id
    assert Decimal(data['price']) == 10


def test_inactive_catalogue_resources_are_hidden(client, customer_headers):
    with SessionLocal() as db:
        country = models.Country(name='Inactive country')
        region = models.Region(name='Inactive region', country=country)
        district = models.District(name='Inactive district', region=region)
        tour = models.Tour(title='Inactive tour', price=10, is_active=False)
        trek = models.Trekking(title='Inactive trek', price=10, is_active=False)
        hotel = models.Hotel(
            name='Inactive hotel', price=10, region=region, district=district, is_active=False
        )
        transport = models.Transport(name='Inactive transport', seats=4, price=10, is_active=False)
        flight = models.HelicopterTour(title='Inactive flight', price=10, is_active=False)
        entries = [
            ('/tours/', tour),
            ('/trekkings/', trek),
            ('/hotels/', hotel),
            ('/transports/', transport),
            ('/helicopter-tours/', flight),
            ('/tour-programs/', models.TourProgram(tour=tour, day_number=1)),
            ('/trekking-programs/', models.TrekkingProgram(trekking=trek, day_number=1)),
            ('/tour-images/', models.TourImage(tour=tour, image='https://example.com/tour.jpg')),
            (
                '/hotel-images/',
                models.HotelImage(hotel=hotel, image='https://example.com/hotel.jpg'),
            ),
            (
                '/transport-images/',
                models.TransportImage(transport=transport, image='https://example.com/van.jpg'),
            ),
            (
                '/trekking-images/',
                models.TrekkingImage(trekking=trek, image='https://example.com/trek.jpg'),
            ),
            (
                '/helicopter-images/',
                models.HelicopterImage(helicopter=flight, image='https://example.com/flight.jpg'),
            ),
        ]
        db.add_all([country, region, district] + [record for _, record in entries])
        db.commit()
        identifiers = [(path, record.id) for path, record in entries]
    for path, record_id in identifiers:
        response = client.get(path, headers=customer_headers)
        assert response.status_code == 200, response.text
        assert all(record['id'] != record_id for record in response.json()), path
        assert client.get(f'{path}{record_id}/', headers=customer_headers).status_code == 404


def test_inactive_public_content_is_hidden(client, admin_headers):
    for path, payload in (
        ('/abouts/', {'title': 'Hidden about', 'is_active': False}),
        ('/about-sections/', {'title': 'Hidden section', 'is_active': False}),
        ('/faqs/', {'question': 'Hidden question', 'answer': 'Hidden answer', 'is_active': False}),
        ('/contacts/', {'city': 'Hidden contact', 'is_active': False}),
    ):
        created = client.post(path, json=payload, headers=admin_headers)
        assert created.status_code == 200, created.text
        item_id = created.json()['id']
        assert all(item['id'] != item_id for item in client.get(path).json())
        if path == '/contacts/':
            assert client.get(f'{path}{item_id}/', headers=admin_headers).status_code == 404
        else:
            assert client.get(f'{path}{item_id}/').status_code == 404


def test_api_updates_translations_and_clears_stale_text_on_failure(
    client, admin_headers, monkeypatch
):
    response = client.post(
        '/faqs/',
        headers=admin_headers,
        json={'question': 'First question', 'answer': 'First answer'},
    )
    record_id = response.json()['id']
    assert client.get(f'/faqs/{record_id}/?lang=en').json()['question'] == 'First question en'
    response = client.put(
        f'/faqs/{record_id}/', headers=admin_headers, json={'question': 'Second question'}
    )
    assert response.status_code == 200
    assert client.get(f'/faqs/{record_id}/?lang=en').json()['question'] == 'Second question en'

    def fail(source):
        raise RuntimeError('Translation provider unavailable')

    monkeypatch.setattr('mysite.translations.content.translate_fields', fail)
    response = client.put(
        f'/faqs/{record_id}/', headers=admin_headers, json={'question': 'Third question'}
    )
    assert response.status_code == 200
    assert client.get(f'/faqs/{record_id}/?lang=en').json()['question'] == 'Third question'


def test_sqladmin_generates_translations(client, admin_headers):
    response = client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    response = client.post(
        '/admin/faq/create',
        data={
            'question': 'Admin translation question',
            'answer': 'Admin answer',
            'order': '0',
            'is_active': 'y',
            'translations': '',
            'save': 'Save',
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    data = client.get('/faqs/?lang=en').json()
    assert any(row['question'] == 'Admin translation question en' for row in data)
    client.get('/admin/logout')


def test_sqladmin_form_preserves_worker_translations_and_explicit_clear_requeues(
    client, admin_headers, monkeypatch
):
    from mysite.database.models import FAQ
    from mysite.translations.jobs import translate_record

    assert client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    ).status_code in (302, 303)
    with SessionLocal() as db:
        record = FAQ(question='Form merge question', answer='Form merge answer', translations={})
        db.add(record)
        db.commit()
        record_id = record.id

    edit_path = f'/admin/faq/edit/{record_id}'
    opened = client.get(edit_path)
    assert opened.status_code == 200

    with SessionLocal() as db:
        record = db.get(FAQ, record_id)
        source = {'question': record.question, 'answer': record.answer}

    def translate(values):
        return {
            lang: {field: f'{value} {lang}' for field, value in values.items()}
            for lang in ('en', 'de', 'zh')
        }

    assert translate_record(FAQ, record_id, source, translate) == 'translated'

    saved = client.post(
        edit_path,
        data={
            'question': source['question'],
            'answer': source['answer'],
            'is_active': 'y',
            'translations': '{}',
            'save': 'Save',
        },
        follow_redirects=False,
    )
    assert saved.status_code in (302, 303), saved.text
    with SessionLocal() as db:
        record = db.get(FAQ, record_id)
        assert record.translations['en']['question'] == 'Form merge question en'

    enqueued = []

    def capture_translation(entity, identity, source, translator):
        enqueued.append((entity, identity, source))
        return True

    monkeypatch.setattr('mysite.admin.views.enqueue_translation', capture_translation)
    cleared = client.post(
        edit_path,
        data={
            'question': source['question'],
            'answer': source['answer'],
            'is_active': 'y',
            'translations': '{"en":{"question":""}}',
            'save': 'Save',
        },
        follow_redirects=False,
    )
    assert cleared.status_code in (302, 303), cleared.text
    with SessionLocal() as db:
        record = db.get(FAQ, record_id)
        assert 'question' not in record.translations['en']
        assert record.translations['en']['answer'] == 'Form merge answer en'
        assert record.translations['en']['_manual_fields'] == []
    assert len(enqueued) == 1
    assert enqueued[0][0] is FAQ and enqueued[0][1] == record_id
    assert enqueued[0][2] == source


def test_sqladmin_stale_empty_translation_does_not_erase_concurrent_worker_update(
    client, admin_headers, monkeypatch
):
    import json

    from sqlalchemy.orm import Session

    from mysite.database.models import FAQ
    from mysite.translations.source import source_field_hash

    assert client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    ).status_code in (302, 303)
    source = {'question': 'Race question', 'answer': 'Race answer'}
    old_translation = 'Older worker translation'
    with SessionLocal() as db:
        record = FAQ(
            **source,
            translations={
                'en': {
                    'question': old_translation,
                    '_source_hashes': {'question': source_field_hash(source['question'])},
                }
            },
        )
        db.add(record)
        db.commit()
        identity = record.id

    edit_path = f'/admin/faq/edit/{identity}'
    assert client.get(edit_path).status_code == 200
    latest_translation = 'New worker translation'
    original_refresh = Session.refresh
    worker_write = []

    def update_worker_before_locked_refresh(session, instance, *args, **kwargs):
        if (
            isinstance(instance, FAQ)
            and instance.id == identity
            and kwargs.get('with_for_update')
            and not worker_write
        ):
            with SessionLocal() as worker_db:
                row = worker_db.get(FAQ, identity)
                row.translations = {
                    'en': {
                        'question': latest_translation,
                        '_source_hashes': {'question': source_field_hash(source['question'])},
                    }
                }
                worker_db.commit()
            worker_write.append(True)
        return original_refresh(session, instance, *args, **kwargs)

    monkeypatch.setattr(Session, 'refresh', update_worker_before_locked_refresh)
    enqueued = []
    monkeypatch.setattr(
        'mysite.admin.views.enqueue_translation', lambda *args: enqueued.append(args)
    )
    stale_form = {
        'en': {
            'question': '',
            '_source_hashes': {'question': source_field_hash(source['question'])},
        }
    }
    response = client.post(
        edit_path,
        data={**source, 'is_active': 'y', 'translations': json.dumps(stale_form), 'save': 'Save'},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303), response.text
    assert worker_write == [True]
    assert enqueued == []
    with SessionLocal() as db:
        saved = db.get(FAQ, identity).translations['en']
        assert saved['question'] == latest_translation
        assert saved['_manual_fields'] == []


def test_tour_rest_put_only_normalizing_line_endings_keeps_translation(
    client, admin_headers, customer_headers
):
    from mysite.translations.source import source_field_hash

    title_crlf = 'Tour title\r\nsecond line'
    title_lf = 'Tour title\nsecond line'
    description_crlf = 'Description\r\nsecond line'
    with SessionLocal() as db:
        tour = models.Tour(title=title_crlf, description=description_crlf, price=10)
        db.add(tour)
        db.flush()
        db.add(
            models.TourTranslation(
                tour_id=tour.id,
                lang='en',
                title='Stable English title',
                description='Stable English description',
                source_hashes={
                    'title': source_field_hash(title_crlf),
                    'description': source_field_hash(description_crlf),
                },
            )
        )
        tour_id = tour.id
        db.commit()

    updated = client.put(f'/tours/{tour_id}/', headers=admin_headers, json={'title': title_lf})
    assert updated.status_code == 200, updated.text
    detail = client.get(f'/tours/{tour_id}/?lang=en', headers=customer_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()['title'] == 'Stable English title'
    assert detail.json()['description'] == 'Stable English description'
    search = client.get('/tours/', params={'lang': 'en', 'search': 'Stable English title'})
    assert search.status_code == 200, search.text
    assert any(item['id'] == tour_id for item in search.json())


def test_seed_demo_is_repeatable_and_preserves_edits(client, customer_headers):
    from seed_demo import seed_demo

    with SessionLocal() as db:
        assert seed_demo(db) > 0
        tour = db.query(models.Tour).filter_by(title='ТЕСТ: Ала-Арча').one()
        tour.price = 123
        db.commit()
        assert seed_demo(db) == 0
        db.refresh(tour)
        assert tour.price == 123
    for path in [
        '/tours/',
        '/hotels/',
        '/transports/',
        '/trekkings/',
        '/helicopter-tours/',
        '/faqs/',
    ]:
        response = client.get(path, params={'lang': 'en'})
        assert response.status_code == 200, response.text
        test_records = [
            row
            for row in response.json()
            if row.get('title', row.get('name', row.get('question', ''))).startswith('TEST:')
        ]
        assert len(test_records) == 20, (path, len(test_records))
        assert len({row['id'] for row in test_records}) == 20
        if path == '/tours/':
            details = [
                client.get(f'/tours/{row["id"]}/', headers=customer_headers).json()
                for row in test_records
            ]
            assert len({(row['latitude'], row['longitude']) for row in details}) == 20
        if path == '/helicopter-tours/':
            for row in test_records:
                assert all(
                    row[field]
                    for field in (
                        'duration_minutes',
                        'max_passengers',
                        'departure_location',
                        'destination',
                        'main_image',
                    )
                )


def test_sqladmin_preserves_manual_translation(client, admin_headers):
    client.post(
        '/admin/login', data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'}
    )
    response = client.post(
        '/admin/faq/create',
        data={
            'question': 'Manual original',
            'answer': 'Original answer',
            'order': '0',
            'is_active': 'y',
            'translations': '{"en":{"question":"Manual English"}}',
            'save': 'Save',
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    assert any(row['question'] == 'Manual English' for row in client.get('/faqs/?lang=en').json())
    client.get('/admin/logout')


def test_nested_tour_program_uses_requested_language(client, customer_headers):
    from mysite.translations.content import mark_manual_translations

    with SessionLocal() as db:
        tour = models.Tour(title='Nested tour', price=10)
        program = models.TourProgram(
            tour=tour,
            day_number=1,
            title='Original program',
            translations=mark_manual_translations(
                {'en': {'title': 'English program'}}, {'title': 'Original program'}
            ),
        )
        db.add_all([tour, program])
        db.commit()
        tour_id = tour.id
    response = client.get(f'/tours/{tour_id}/?lang=en', headers=customer_headers)
    assert response.status_code == 200
    assert response.json()['programs'][0]['title'] == 'English program'


def test_tour_admin_hooks_refresh_translations_and_remove_stale_values(
    client, customer_headers, monkeypatch
):
    import asyncio
    from types import SimpleNamespace

    from mysite.admin.views import TourAdmin

    view = TourAdmin()
    with SessionLocal() as db:
        tour = models.Tour(title='Before admin edit', price=10)
        db.add(tour)
        db.commit()
        tour_id = tour.id
        db.add(models.TourTranslation(tour_id=tour_id, lang='en', title='Stale English'))
        db.commit()
        request = SimpleNamespace(state=SimpleNamespace())
        asyncio.run(view.on_model_change({'title': 'After admin edit'}, tour, False, request))
        tour.title = 'After admin edit'
        db.commit()
        monkeypatch.setattr(
            'mysite.api.tour.translate_tour',
            lambda source: {
                lang: dict(source, title='Fresh English') for lang in ('en', 'de', 'zh')
            },
        )
        asyncio.run(view.after_model_change({}, tour, False, request))
    assert (
        client.get(f'/tours/{tour_id}/?lang=en', headers=customer_headers).json()['title']
        == 'Fresh English'
    )

    def fail(source):
        raise RuntimeError('Translation provider unavailable')

    monkeypatch.setattr('mysite.api.tour.translate_tour', fail)
    with SessionLocal() as db:
        tour = db.get(models.Tour, tour_id)
        asyncio.run(view.on_model_change({'title': 'New source'}, tour, False, request))
        tour.title = 'New source'
        db.commit()
        asyncio.run(view.after_model_change({}, tour, False, request))
    assert (
        client.get(f'/tours/{tour_id}/?lang=en', headers=customer_headers).json()['title']
        == 'New source'
    )


def test_seed_fills_all_content_sections_and_galleries(client):
    from seed_demo import seed_demo

    content_models = [
        models.About,
        models.AboutSection,
        models.Country,
        models.Region,
        models.District,
        models.TourCategory,
        models.Contact,
        models.TravelRequest,
    ]
    with SessionLocal() as db:
        seed_demo(db)
        for model in content_models:
            assert db.query(model).count() >= 20, model.__name__
        for parent, image_model, foreign_key in [
            (models.Tour, models.TourImage, 'tour_id'),
            (models.Hotel, models.HotelImage, 'hotel_id'),
            (models.Transport, models.TransportImage, 'transport_id'),
            (models.Trekking, models.TrekkingImage, 'trekking_id'),
            (models.HelicopterTour, models.HelicopterImage, 'helicopter_id'),
        ]:
            title = getattr(parent, 'title', None)
            field = title if title is not None else parent.name
            records = db.query(parent).filter(field.like('ТЕСТ:%')).all()
            assert len(records) == 20
            for row in records:
                assert row.main_image.startswith('https://picsum.photos/')
                images = (
                    db.query(image_model).filter(getattr(image_model, foreign_key) == row.id).all()
                )
                assert images, (parent.__name__, row.id)
                assert all(image.image.startswith('https://') for image in images)
        for program in [models.TourProgram, models.TrekkingProgram]:
            assert db.query(program).count() >= 20
        counts = {
            table.name: db.query(table).count() for table in models.Base.metadata.sorted_tables
        }
        seed_demo(db)
        assert counts == {
            table.name: db.query(table).count() for table in models.Base.metadata.sorted_tables
        }


def test_extended_seed_has_translated_reference_and_contact_fields(client):
    from seed_demo import seed_demo

    with SessionLocal() as db:
        seed_demo(db)
        country = db.query(models.Country).filter_by(name='ТЕСТ: Страна 02').one()
        assert country.translations['en']['name'] == 'TEST: Country 02'
        assert country.translations['de']['name'] == 'TEST: Land 02'
        assert country.translations['zh']['name'] == '测试: 国家 02'
        contact = db.query(models.Contact).filter_by(email='test-office-02@example.com').one()
        assert contact.translations['de']['city'] == 'TEST: Stadt 02'
        assert contact.translations['zh']['city'] == '测试: 城市 02'
        tour = db.query(models.Tour).filter_by(title='ТЕСТ: Ала-Арча').one()
        assert all(row.included and row.excluded for row in tour.translations)


def test_seed_completes_every_content_field_and_translation(client):
    from mysite.translations.content import CONTENT_FIELDS
    from seed_demo import seed_demo

    with SessionLocal() as db:
        seed_demo(db)
        for model in (models.Hotel, models.Transport, models.Trekking, models.HelicopterTour):
            field = model.title if hasattr(model, 'title') else model.name
            records = db.query(model).filter(field.like('ТЕСТ:%')).all()
            for record in records:
                for column in model.__table__.columns:
                    assert getattr(record, column.key) not in (None, ''), (
                        model.__name__,
                        column.key,
                    )
                for lang in ('en', 'de', 'zh'):
                    for key in CONTENT_FIELDS[model.__tablename__]:
                        assert record.translations.get(lang, {}).get(key), (
                            model.__name__,
                            lang,
                            key,
                        )
        contacts = (
            db.query(models.Contact)
            .filter(models.Contact.email.like('test-office-%@example.com'))
            .all()
        )
        assert len(contacts) == 20
        assert all('create-qr-code' in row.qr_code for row in contacts)
        hotel = db.query(models.Hotel).filter(models.Hotel.name.like('ТЕСТ:%')).first()
        hotel.translations = dict(
            hotel.translations, en=dict(hotel.translations['en'], address='Manual address')
        )
        hotel.main_image = 'https://example.invalid/my-manual-image.jpg'
        db.commit()
        seed_demo(db)
        db.refresh(hotel)
        assert hotel.translations['en']['address'] == 'Manual address'
        assert hotel.main_image == 'https://example.invalid/my-manual-image.jpg'


def test_sqladmin_saved_whitespace_translation_is_cleared_and_enqueued_only_once(
    client, admin_headers, monkeypatch
):
    import json

    from mysite.database.models import FAQ
    from mysite.translations.source import source_field_hash

    assert client.post(
        '/admin/login',
        data={'username': 'test-admin', 'password': 'StrongAdminPassword123!'},
        follow_redirects=False,
    ).status_code in (302, 303)
    translations = {
        'en': {
            'question': '\u00a0\n\t',
            'answer': 'Preserved answer',
            '_source_hashes': {
                'question': source_field_hash('Whitespace question'),
                'answer': source_field_hash('Whitespace answer'),
            },
            '_manual_fields': ['question'],
        }
    }
    with SessionLocal() as db:
        record = FAQ(
            question='Whitespace question', answer='Whitespace answer', translations=translations
        )
        db.add(record)
        db.commit()
        identity = record.id
    path = f'/admin/faq/edit/{identity}'
    assert client.get(path).status_code == 200
    enqueued = []
    monkeypatch.setattr(
        'mysite.admin.views.enqueue_translation', lambda *args: enqueued.append(args)
    )
    data = {
        'question': 'Whitespace question',
        'answer': 'Whitespace answer',
        'is_active': 'y',
        'translations': json.dumps(translations),
        'save': 'Save',
    }
    for _ in range(2):
        response = client.post(path, data=data, follow_redirects=False)
        assert response.status_code in (302, 303), response.text
    assert len(enqueued) == 1
    assert enqueued[0][0] is FAQ and enqueued[0][1] == identity
    with SessionLocal() as db:
        saved = db.get(FAQ, identity).translations['en']
        assert 'question' not in saved
        assert 'question' not in saved['_source_hashes']
        assert 'question' not in saved['_manual_fields']
        assert saved['answer'] == 'Preserved answer'
    client.get('/admin/logout')
