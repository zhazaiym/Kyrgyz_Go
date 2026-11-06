from ML.tools import search_tours


def test_invalid_people_count():
    result = search_tours.invoke({
        "people_count": 0
    })
    assert result == []


def test_invalid_duration():
    result = search_tours.invoke({
        "duration_days": -1
    })
    assert result == []
