from ML.tools import search_tours


def test_invalid_people_count():
    result = search_tours.invoke({'people_count': 0})
    assert result == []


def test_invalid_duration():
    result = search_tours.invoke({'duration_days': -1})
    assert result == []


def test_invalid_filters_do_not_import_database(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith('mysite.database'):
            raise AssertionError('Invalid filters must not load database configuration')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    assert search_tours.invoke({'people_count': 0}) == []
    assert search_tours.invoke({'duration_days': -1}) == []
