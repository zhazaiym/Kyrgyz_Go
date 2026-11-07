import pytest

from ML.tools import search_tours
from mysite.database.models import Tour
from tests import test_company_tools

isolated_catalogue = test_company_tools.company_database


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
