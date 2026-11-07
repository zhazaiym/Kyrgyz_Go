"""Catalogue tools the chat model sees: tours, helicopter tours and trekking."""

import pytest

from ML import tools
from mysite.database.models import (Country, HelicopterTour, Tour, TourProgram, Trekking,
                                    TrekkingProgram)
from tests import test_company_tools

catalogue = test_company_tools.company_database


def _ids(result, kind=None):
    return [(item['kind'], item['id']) for item in result['items'] if kind in (None, item['kind'])]


def _seed_each_kind(db):
    records = {
        'tour': [
            Tour(title='Горный тур', price=100, duration_days=3, min_people=1, max_people=6),
            Tour(title='Скрытый тур', price=100, is_active=False),
            Tour(title='ТЕСТ: демо тур', price=100),
        ],
        'helicopter_tour': [
            HelicopterTour(
                title='Полёт над ледником',
                price=900,
                destination='Ледник Иныльчек',
                departure_location='Каракол',
                duration_minutes=40,
                max_passengers=4,
            ),
            HelicopterTour(title='Скрытый полёт', price=900, is_active=False),
            HelicopterTour(title='TEST: demo flight', price=900),
        ],
        'trekking': [
            Trekking(
                title='Треккинг к озеру',
                price=80,
                route='Ущелье - озеро',
                duration_days=2,
                difficulty='средняя',
                distance_km=18.5,
                max_altitude=3500,
                min_people=2,
                max_people=10,
            ),
            Trekking(title='Скрытый треккинг', price=80, is_active=False),
            Trekking(title='Тест: демо треккинг', price=80),
        ],
    }
    for rows in records.values():
        db.add_all(rows)
    db.commit()
    return {kind: [row.id for row in rows] for kind, rows in records.items()}


def test_each_kind_is_found_without_inactive_or_demo_records(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        ids = _seed_each_kind(db)
    result = tools.search_catalogue.invoke({})
    assert _ids(result) == [
        ('tour', ids['tour'][0]),
        ('helicopter_tour', ids['helicopter_tour'][0]),
        ('trekking', ids['trekking'][0]),
    ]
    assert result['total'] == 3
    assert result['has_more'] is False
    for kind, rows in ids.items():
        filtered = tools.search_catalogue.invoke({'kind': kind})
        assert _ids(filtered) == [(kind, rows[0])]


def test_items_keep_their_own_fields_and_null_for_missing(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        _seed_each_kind(db)
    items = {item['kind']: item for item in tools.search_catalogue.invoke({})['items']}
    flight = items['helicopter_tour']
    assert flight['duration_minutes'] == 40
    assert flight['max_passengers'] == 4
    assert flight['destination'] == 'Ледник Иныльчек'
    assert 'duration_days' not in flight
    trek = items['trekking']
    assert trek['duration_days'] == 2
    assert trek['duration_hours'] is None
    assert trek['difficulty'] == 'средняя'
    assert trek['distance_km'] == '18.50'
    tour = items['tour']
    assert tour['duration_days'] == 3
    assert tour['country'] is None
    for item in items.values():
        assert {'kind', 'id', 'title', 'price', 'price_unit', 'currency', 'description'} <= set(
            item
        )


def test_day_filters_do_not_apply_to_helicopter_tours(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        ids = _seed_each_kind(db)
    result = tools.search_catalogue.invoke({'duration_days': 2})
    assert _ids(result) == [
        ('helicopter_tour', ids['helicopter_tour'][0]),
        ('trekking', ids['trekking'][0]),
    ]
    assert _ids(tools.search_catalogue.invoke({'min_duration_days': 3})) == [
        ('tour', ids['tour'][0]),
        ('helicopter_tour', ids['helicopter_tour'][0]),
    ]


def test_group_size_uses_each_kind_capacity(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        ids = _seed_each_kind(db)
    assert _ids(tools.search_catalogue.invoke({'people_count': 5})) == [
        ('tour', ids['tour'][0]),
        ('trekking', ids['trekking'][0]),
    ]
    assert _ids(tools.search_catalogue.invoke({'people_count': 1})) == [
        ('tour', ids['tour'][0]),
        ('helicopter_tour', ids['helicopter_tour'][0]),
    ]


def test_catalogue_limit_reports_total_and_has_more(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        db.add_all([Tour(title=f'Route {index}', price=100) for index in range(31)])
        db.commit()
    result = tools.search_catalogue.invoke({})
    assert tools.CATALOGUE_LIMIT == 30
    assert len(result['items']) == 30
    assert [item['title'] for item in result['items']] == [f'Route {i}' for i in range(30)]
    assert result['total'] == 31
    assert result['has_more'] is True


def test_listing_reads_one_query_per_kind_without_programs(catalogue):
    from sqlalchemy import event

    sessions, engine = catalogue
    with sessions() as db:
        _seed_each_kind(db)
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        tools.search_catalogue.invoke({})
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert not [s for s in statements if 'programs' in s]
    assert len(statements) <= 6


def test_catalogue_item_details_for_each_kind(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        ids = _seed_each_kind(db)
        tour = db.get(Tour, ids['tour'][0])
        tour.included = 'Гид'
        tour.country = Country(name='Кыргызстан')
        db.add(TourProgram(tour_id=tour.id, day_number=1, title='День 1', description='Выезд'))
        flight = db.get(HelicopterTour, ids['helicopter_tour'][0])
        flight.instruction = 'Лёгкая одежда'
        flight.included = 'Трансфер'
        trek = db.get(Trekking, ids['trekking'][0])
        trek.requirements = 'Ботинки'
        db.add(TrekkingProgram(trekking_id=trek.id, day_number=1, title='Подъём'))
        db.commit()

    detail = tools.get_catalogue_item.invoke({'kind': 'tour', 'id': ids['tour'][0]})
    assert detail['kind'] == 'tour'
    assert detail['included'] == 'Гид'
    assert detail['country'] == 'Кыргызстан'
    assert detail['program'] == [{'day': 1, 'title': 'День 1', 'description': 'Выезд'}]

    detail = tools.get_catalogue_item.invoke(
        {'kind': 'helicopter_tour', 'id': ids['helicopter_tour'][0]}
    )
    assert detail['destination'] == 'Ледник Иныльчек'
    assert detail['departure_location'] == 'Каракол'
    assert detail['instruction'] == 'Лёгкая одежда'
    assert detail['included'] == 'Трансфер'

    detail = tools.get_catalogue_item.invoke({'kind': 'trekking', 'id': ids['trekking'][0]})
    assert detail['route'] == 'Ущелье - озеро'
    assert detail['requirements'] == 'Ботинки'
    assert detail['max_altitude'] == 3500
    assert detail['program'] == [{'day': 1, 'title': 'Подъём', 'description': None}]


def test_catalogue_item_not_found_for_hidden_foreign_kind_or_missing_id(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        ids = _seed_each_kind(db)
        only_tour = Tour(title='Только тур', price=100)
        db.add(only_tour)
        db.commit()
        only_tour_id = only_tour.id
    for kind, rows in ids.items():
        for hidden in rows[1:]:
            assert 'error' in tools.get_catalogue_item.invoke({'kind': kind, 'id': hidden})
    assert 'error' not in tools.get_catalogue_item.invoke({'kind': 'tour', 'id': only_tour_id})
    assert 'error' in tools.get_catalogue_item.invoke({'kind': 'trekking', 'id': only_tour_id})
    assert 'error' in tools.get_catalogue_item.invoke({'kind': 'tour', 'id': 999_999})


def test_unknown_kind_is_rejected_as_tool_input():
    for tool, args in (
        (tools.get_catalogue_item, {'kind': 'hotel', 'id': 1}),
        (tools.search_catalogue, {'kind': 'hotel'}),
    ):
        result = tool.invoke(args)
        assert 'error' in str(result)
        assert 'helicopter_tour' in str(result)


def test_model_sees_only_new_catalogue_tools():
    names = {tool.name for tool in tools.READ_TOOLS}
    assert {'search_catalogue', 'get_catalogue_item'} <= names
    assert not {'search_tours', 'list_active_tours', 'get_tour_details'} & names
    for old in ('search_tours', 'list_active_tours', 'get_tour_details'):
        assert not hasattr(tools, old)


@pytest.mark.parametrize('title', ['50%off', 'tour_name', r'path\trail'])
def test_search_preserves_literal_like_metacharacters(catalogue, title):
    sessions, _ = catalogue
    with sessions() as db:
        db.add_all([Tour(title=title, price=100), Tour(title='ordinary', price=100)])
        db.commit()
    result = tools.search_catalogue.invoke({'destination': title})
    assert [item['title'] for item in result['items']] == [title]
