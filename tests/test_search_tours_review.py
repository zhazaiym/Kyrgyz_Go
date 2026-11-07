import pytest

from ML.tools import list_active_tours, search_tours
from mysite.database.models import Country, Tour
from tests import test_company_tools

isolated_catalogue = test_company_tools.company_database


def test_catalogue_entry_points_return_first_thirty_public_tours(isolated_catalogue):
    sessions, _ = isolated_catalogue
    with sessions() as db:
        db.add_all(
            [
                Tour(title='Hidden', price=100, is_active=False),
                Tour(title='Тест: demo', price=100),
                *[Tour(title=f'Route {index}', price=100) for index in range(31)],
            ]
        )
        db.commit()
    expected = [f'Route {index}' for index in range(30)]
    assert [row['title'] for row in search_tours.invoke({})] == expected
    assert [row['title'] for row in list_active_tours.invoke({})] == expected


@pytest.mark.parametrize('field', ['title', 'description', 'country'])
@pytest.mark.parametrize(
    'stored, destination',
    [
        ('Каракол', 'Karakol'),
        ('KARAKOL', 'Каракол'),
        ('Сон-Көл', 'Song-Kol'),
        ('Сонкуль', 'Song Kol'),
        ('Сон-Куль', 'SONG–KOL'),
        ('Song-Kol', 'Сонкуль'),
        ('Song Kol', 'Сон-Көл'),
    ],
)
def test_destination_aliases_match_both_scripts(isolated_catalogue, field, stored, destination):
    sessions, _ = isolated_catalogue
    with sessions() as db:
        tour = Tour(title='Mountain route', description='Scenic route', price=100)
        if field == 'country':
            tour.country = Country(name=stored)
        else:
            setattr(tour, field, stored)
        db.add_all([tour, Tour(title='Unrelated destination', price=100)])
        db.commit()
        identity = tour.id
    assert [row['id'] for row in search_tours.invoke({'destination': destination})] == [identity]


@pytest.mark.parametrize('destination', ['Issyk-Kul', 'Ысык-Көл', 'Иссык Куль', 'ИССЫК-КУЛЬ'])
def test_destination_aliases_find_existing_tour(isolated_catalogue, destination):
    sessions, _ = isolated_catalogue
    with sessions() as db:
        tour = Tour(title='Иссык-Куль', description='Озёрный маршрут', duration_days=6, price=100)
        db.add(tour)
        db.commit()
        identity = tour.id
    result = search_tours.invoke({'destination': destination})
    assert identity in [item['id'] for item in result]


def test_duration_range_includes_six_days_without_relaxing_exact_duration(isolated_catalogue):
    sessions, _ = isolated_catalogue
    with sessions() as db:
        db.add_all(
            [
                Tour(title='Six days', duration_days=6, price=100),
                Tour(title='Eight days', duration_days=8, price=100),
            ]
        )
        db.commit()
    result = search_tours.invoke({'min_duration_days': 6, 'max_duration_days': 7})
    assert [item['title'] for item in result] == ['Six days']
    assert search_tours.invoke({'duration_days': 7}) == []


@pytest.mark.parametrize('title', ['50%off', 'tour_name', r'path\trail'])
def test_search_preserves_literal_like_metacharacters(isolated_catalogue, title):
    sessions, _ = isolated_catalogue
    with sessions() as db:
        db.add_all([Tour(title=title, price=100), Tour(title='ordinary', price=100)])
        db.commit()
    assert [item['title'] for item in search_tours.invoke({'destination': title})] == [title]
