from ML.tools import search_catalogue

EMPTY = {'items': [], 'total': 0, 'has_more': False}


def test_invalid_people_count():
    assert search_catalogue.invoke({'people_count': 0}) == EMPTY


def test_invalid_duration():
    assert search_catalogue.invoke({'duration_days': -1}) == EMPTY


def test_invalid_filters_do_not_import_database(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith('mysite.database'):
            raise AssertionError('Invalid filters must not load database configuration')
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded_import)
    assert search_catalogue.invoke({'people_count': 0}) == EMPTY
    assert search_catalogue.invoke({'duration_days': -1}) == EMPTY
    assert search_catalogue.invoke({'min_duration_days': 8, 'max_duration_days': 7}) == EMPTY
    assert search_catalogue.invoke({'max_duration_days': 0}) == EMPTY
