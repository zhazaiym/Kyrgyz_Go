"""Destination search table: scripts, Kyrgyz letters, typos, translations and keywords."""

import pytest
from sqlalchemy import literal, select

from ML import tools
from mysite.database.db import SessionLocal as SessionLocalForApi
from mysite.database.models import Country, HelicopterTour, Tour, TourTranslation, Trekking
from tests import test_company_tools

catalogue = test_company_tools.company_database


@pytest.fixture
def places(catalogue):
    sessions, engine = catalogue
    with sessions() as db:
        rows = {
            'issyk': Tour(
                title='Иссык-Куль: южный берег',
                description='Пляжи, Сказка и горячие источники',
                price=300,
                duration_days=4,
            ),
            'karakol': Tour(
                title='Каракол и ущелье Джети-Огуз',
                description='Красные скалы и ели',
                price=250,
                duration_days=3,
            ),
            'song': Tour(
                title='Сон-Куль: юрты и кони',
                description='Высокогорный джайлоо',
                price=200,
                duration_days=2,
            ),
            'bishkek': Tour(
                title='Бишкек: обзорная экскурсия',
                description='Площадь Ала-Тоо и Ошский базар',
                price=50,
                duration_days=1,
            ),
            'archa': Trekking(
                title='Пик Байчечекей',
                description='Подъём к водопаду',
                route='Ала-Арча: альплагерь - водопад Ак-Сай',
                price=60,
                duration_days=1,
            ),
            'flight': HelicopterTour(
                title='Полёт над ледником',
                description='Вид на пик Хан-Тенгри',
                destination='Иныльчек',
                departure_location='Каракол',
                price=900,
                translations={'en': {'title': 'Glacier flight', '_source_hashes': {'t': 'abc'}}},
            ),
            'keyword': Trekking(
                title='Озеро в горах',
                description='Однодневный маршрут',
                price=40,
                search_keywords='Кол-Укок, Kol Ukok',
            ),
        }
        db.add_all(rows.values())
        db.flush()
        db.add(TourTranslation(tour_id=rows['song'].id, lang='de', title='Song-Kul-See: Jurten'))
        db.commit()
        yield {name: (_kind(row), row.id) for name, row in rows.items()}


def _kind(row):
    return {Tour: 'tour', Trekking: 'trekking', HelicopterTour: 'helicopter_tour'}[type(row)]


def _found(destination, **extra):
    result = tools.search_catalogue.invoke({'destination': destination, **extra})
    return [(item['kind'], item['id']) for item in result['items']]


@pytest.mark.parametrize(
    'query',
    ['Issyk-Kul', 'Issyk Kul', 'Иссык Куль', 'Ысык-Көл', 'иссыккульь', 'ИССЫК-КУЛЬ', 'Issyk–Kul'],
)
def test_issyk_kul_spellings_find_the_lake_tour(places, query):
    found = _found(query)
    assert found[0] == places['issyk'], found
    assert places['bishkek'] not in found


@pytest.mark.parametrize('query', ['Karakol', 'Каракол', 'каракольское ущелье', 'KARAKOL'])
def test_karakol_spellings(places, query):
    found = _found(query)
    assert places['karakol'] in found, found
    assert places['issyk'] not in found and places['bishkek'] not in found


@pytest.mark.parametrize('query', ['Song-Kol', 'Сон-Көл', 'Сонкуль', 'Song Kul', 'SONG–KOL'])
def test_song_kul_spellings(places, query):
    found = _found(query)
    assert found[0] == places['song'], found
    assert places['issyk'] not in found


@pytest.mark.parametrize('query', ['Ala-Archa', 'Ала-Арча', 'ала арча'])
def test_ala_archa_finds_trekking_by_route(places, query):
    found = _found(query)
    assert found[0] == places['archa'], found
    assert _found(query, kind='tour') == []


def test_search_keywords_participate(places):
    assert _found('Кол-Укок') == [places['keyword']]
    assert _found('Kol-Ukok') == [places['keyword']]


def test_translations_and_geo_fields_are_searched(places):
    assert _found('Glacier') == [places['flight']]
    assert _found('Jurten') == [places['song']]
    assert _found('Иныльчек') == [places['flight']]
    assert places['flight'] in _found('Каракол')


def test_translation_hashes_are_not_searched(places):
    assert _found('abc') == []


def test_bishkek_does_not_find_issyk_kul(places):
    found = _found('Бишкек')
    assert found == [places['bishkek']]


@pytest.mark.parametrize('query', ['Париж', 'zzzz', 'Самарканд'])
def test_unrelated_places_find_nothing(places, query):
    assert _found(query) == []


def test_country_name_is_searched(catalogue):
    sessions, _ = catalogue
    with sessions() as db:
        tour = Tour(title='Маршрут', price=1, country=Country(name='Узбекистан'))
        db.add_all([tour, Tour(title='Другой', price=1)])
        db.commit()
        identity = tour.id
    assert _found('Uzbekistan') == [('tour', identity)]


def test_filters_still_apply_to_destination_matches(places):
    assert _found('Issyk-Kul', duration_days=3) == []
    assert _found('Issyk-Kul', kind='trekking') == []
    assert _found('Каракол', kind='helicopter_tour') == [places['flight']]


@pytest.mark.parametrize('title', ['50%off', 'tour_name', r'path\trail'])
def test_like_metacharacters_are_literal(catalogue, title):
    sessions, _ = catalogue
    with sessions() as db:
        db.add_all([Tour(title=title, price=100), Tour(title='ordinary', price=100)])
        db.commit()
    assert [
        item['title'] for item in tools.search_catalogue.invoke({'destination': title})['items']
    ] == [title]
    for symbol in ('%', '_', '\\'):
        expected = [title] if symbol in title else []
        found = tools.search_catalogue.invoke({'destination': symbol})['items']
        assert [item['title'] for item in found] == expected, symbol


@pytest.mark.parametrize(
    'value',
    [
        'Иссык-Куль',
        'ЫСЫК-КӨЛ',
        'Сон–Көл',
        'Ёлка  Ңаryn',
        'Ысык Ата',
        'Köl Über Straße',
        'Ørsted Æble',
        'path\\trail_50%',
        '天山 Tian-Shan',
        'Тоо Ашуу',
        'Подъезд к ущелью',
    ],
)
def test_python_and_sql_normalization_are_identical(catalogue, value):
    sessions, _ = catalogue
    with sessions() as db:
        sql = db.execute(select(tools._normalized_sql(literal(value)))).scalar_one()
    assert sql == tools.normalize_search_text(value)


def test_normalization_rules():
    normalize = tools.normalize_search_text
    assert normalize('Ысык-Көл') == normalize('ысык кол')
    assert normalize('Ёлка') == normalize('елка')
    assert normalize('Үч-Ңаак') == normalize('уч наак')
    assert normalize('Иссык-Куль') == normalize('иссыккульь')
    assert ' ' not in normalize('a b-c')


def test_old_alias_lists_are_gone():
    for name in (
        '_LAKE_ALIASES',
        '_DESTINATION_ALIASES',
        '_destination_key',
        '_destination_column',
    ):
        assert not hasattr(tools, name)


def test_migration_installs_extensions_and_keyword_columns():
    from sqlalchemy import inspect, text

    from mysite.database.db import engine

    with engine.connect() as connection:
        installed = set(
            connection.execute(
                text("SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent')")
            ).scalars()
        )
    assert installed == {'pg_trgm', 'unaccent'}
    columns = inspect(engine)
    for table in ('tours', 'helicopter_tours', 'trekkings'):
        keyword = {c['name']: c for c in columns.get_columns(table)}['search_keywords']
        assert keyword['nullable'] is True


def test_admin_edits_search_keywords_without_translating_them():
    from mysite.admin.views import HelicopterTourAdmin, TourAdmin, TrekkingAdmin
    from mysite.translations.content import CONTENT_FIELDS
    from mysite.translations.source import TOUR_TRANSLATION_FIELDS

    for view in (TourAdmin, HelicopterTourAdmin, TrekkingAdmin):
        assert 'search_keywords' in view.form_args
        assert 'search_keywords' not in getattr(view, 'form_excluded_columns', [])
    assert 'search_keywords' not in TOUR_TRANSLATION_FIELDS
    assert 'search_keywords' not in CONTENT_FIELDS['helicopter_tours']
    assert 'search_keywords' not in CONTENT_FIELDS['trekkings']


def test_public_catalogue_api_does_not_expose_search_keywords(client):
    with SessionLocalForApi() as db:
        db.add(HelicopterTour(title='Публичный полёт', price=1, search_keywords='секрет-кейворд'))
        db.commit()
    response = client.get('/helicopter-tours/')
    assert response.status_code == 200
    assert 'секрет-кейворд' not in response.text
