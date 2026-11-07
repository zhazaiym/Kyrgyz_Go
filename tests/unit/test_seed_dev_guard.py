import pytest


@pytest.mark.parametrize(
    'url',
    [
        'postgresql://user@production.example/kyrgyzgo_dev',
        'postgresql://user@127.0.0.1/production',
        'postgresql://user@localhost/kyrgyzgo',
        'postgresql:///kyrgyzgo_dev',
        'sqlite:///dev.db',
    ],
)
def test_development_seed_refuses_non_local_or_non_development_databases(url):
    from scripts.seed_dev import validate_dev_database

    with pytest.raises(ValueError):
        validate_dev_database(url)


def test_development_seed_accepts_explicit_loopback_development_database():
    from scripts.seed_dev import validate_dev_database

    validate_dev_database('postgresql://user@127.0.0.1:5432/kyrgyzgo_dev')
