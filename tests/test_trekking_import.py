"""Import regression tests use disposable PostgreSQL and synthetic test prices."""

from copy import deepcopy

import pytest
from sqlalchemy import func, select

from mysite.database.db import SessionLocal
from mysite.database.models import Trekking
from mysite.translations.content import localized
from scripts import import_trekkings as importer
from scripts.trekking_data import LANGUAGES, ROUTES


@pytest.mark.parametrize(
    'url',
    [
        'sqlite:///kyrgyzgo.db',
        'postgresql://localhost/test_kyrgyzgo_any',
        'postgresql://localhost/kyrgyzgo_prod',
        'postgresql://remote.example/kyrgyzgo.db',
        'postgresql://localhost/kyrgyzgo.db?host=remote.example',
        'postgresql://localhost/another_database',
    ],
)
def test_import_refuses_unsafe_target(url):
    with pytest.raises(ValueError):
        importer.validate_target(url, 'kyrgyzgo.db')


def test_loopback_postgresql_with_exact_name_is_accepted():
    assert (
        importer.validate_target('postgresql://localhost/kyrgyzgo.db', 'kyrgyzgo.db').host
        == 'localhost'
    )


@pytest.mark.parametrize(
    'value',
    [
        None,
        {},
        {'price': 0},
        {'approved_by_company': True, 'price': 'NaN'},
        {'approved_by_company': True, 'price': '100', 'price_unit': 'invalid'},
        {'approved_by_company': True, 'price': '0', 'price_unit': 'per_person', 'min_people': 1},
        {
            'approved_by_company': True,
            'price': '100.001',
            'price_unit': 'per_person',
            'min_people': 1,
        },
    ],
)
def test_no_zero_or_missing_commercial_data(value):
    with pytest.raises(ValueError):
        importer.validate_commercial(value)


def test_existing_model_defaults_are_not_additional_required_inputs():
    values = importer.validate_commercial({'approved_by_company': True, 'price': '123.45'})
    assert values['price_unit'] == 'per_person'
    assert values['min_people'] == 1
    assert values['max_people'] is None


def test_estimates_have_sources_currency_and_four_language_disclaimers():
    from scripts.trekking_prices import estimates

    pricing = estimates()
    assert len(pricing) == 13
    for route in ROUTES:
        if route['key'] not in pricing:
            continue
        estimate = pricing[route['key']]
        assert importer.validate_commercial(estimate)['price'] > 0
        values = importer.record_values(route, estimate)
        row = Trekking(**values)
        for lang in LANGUAGES:
            description = localized(row, lang)['description']
            assert importer.estimate_note(estimate, lang) in description
            assert 'KGS' in description
        assert values['included'] is None
        assert values['is_active'] is False
        assert values['translations']['_trekking_import']['price_estimate'] == estimate


def test_undocumented_estimate_cannot_authorize_a_price():
    with pytest.raises(ValueError):
        importer.validate_commercial(dict(price='100', is_estimate=True, authorized_estimate=True))


def test_estimated_draft_readable_through_existing_admin_loader(monkeypatch):
    from mysite.database.db import engine
    from scripts.trekking_prices import estimates

    route = deepcopy(ROUTES[1])
    route['key'] = 'admin-estimate-test'
    route['content']['ru']['title'] = 'Проверка просмотра неактивного черновика'
    monkeypatch.setattr(importer, 'ROUTES', [route])
    price = estimates()['jeti-oguz-ala-kul-5d']
    with SessionLocal() as db:
        created = importer.import_rows(db, {route['key']: price}, apply=True)
        db.commit()
    record = importer.admin_probe(engine, [created[0]['id']])[0]
    assert record['is_active'] is False
    assert record['currency'] == 'KGS'
    assert len(record['program_ids']) == 5
    assert len(record['image_ids']) == 1
    assert record['translation_languages'] == list(LANGUAGES)


def test_dataset_has_fifteen_sourced_multilingual_itineraries():
    assert len(ROUTES) == len({r['key'] for r in ROUTES}) == 15
    for route in ROUTES:
        assert route['price'] is None and route['price_unit'] is None
        assert route['is_active'] is False
        assert route['duration_days'] == len(route['programs'])
        assert [p['day_number'] for p in route['programs']] == list(
            range(1, route['duration_days'] + 1)
        )
        assert route['sources'] and all(url.startswith('https://') for url in route['sources'])
        assert set(route['content']) == set(LANGUAGES)
        for lang, values in route['content'].items():
            assert values['title'] and values['description'] and values['route']
            assert values['included'] is None


def test_missing_prices_do_not_insert_even_when_apply_requested():
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Trekking))
        results = importer.import_rows(db, {}, apply=True)
        assert any(item['status'] == 'blocked' for item in results)
        assert db.scalar(select(func.count()).select_from(Trekking)) == before
        db.rollback()


def test_import_is_add_only_idempotent_and_uses_existing_translations(monkeypatch):
    route = deepcopy(ROUTES[0])
    route['key'] = 'test-import-synthetic-price'
    route['content']['ru']['title'] = 'Тест идемпотентности импорта Trekking'
    monkeypatch.setattr(importer, 'ROUTES', [route])
    commercial = {
        route['key']: dict(
            approved_by_company=True, price='123.45', price_unit='per_person', min_people=1
        )
    }
    with SessionLocal() as db:
        first = importer.import_rows(db, commercial, apply=True)
        assert first[0]['status'] == 'created_draft'
        identity = first[0]['id']
        db.commit()
    with SessionLocal() as db:
        row = db.get(Trekking, identity)
        row.description = 'User-edited description must survive repeat import'
        db.commit()
    with SessionLocal() as db:
        second = importer.import_rows(db, commercial, apply=True)
        assert second == [dict(key=route['key'], id=identity, status='existing_untouched')]
        row = db.get(Trekking, identity)
        assert row.description == 'User-edited description must survive repeat import'
        assert len(row.programs) == route['duration_days']
        assert len(row.images) == 1
        assert not row.is_active
        for lang in ('en', 'de', 'zh'):
            assert localized(row, lang)['title'] == route['content'][lang]['title']
            for program in row.programs:
                assert (
                    localized(program, lang)['title']
                    == route['programs'][program.day_number - 1]['content'][lang]['title']
                )
        db.rollback()
