from mysite.database.db import SessionLocal
from mysite.database.models import Tour
from scripts.seed_dev import seed_development


def test_development_catalogue_seed_is_repeatable():
    with SessionLocal() as db:
        first = seed_development(db)
        second = seed_development(db)
        assert first == second
        assert db.query(Tour).filter_by(title='[DEV] Вымышленный поход').count() == 1
