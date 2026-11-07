"""Repeatable fictional catalogue for explicitly local development databases."""

import argparse
import os

from sqlalchemy.engine import make_url


def validate_dev_database(value):
    url = make_url(value)
    if (
        url.get_backend_name() != 'postgresql'
        or url.host not in {'127.0.0.1', 'localhost', '::1'}
        or not (
            url.database == 'kyrgyzgo_dev'
            or (url.database or '').startswith(('kyrgyzgo_dev_', 'test_kyrgyzgo_'))
        )
    ):
        raise ValueError(
            'Seed refused: use an explicit loopback PostgreSQL development/test database'
        )


def seed_development(db):
    validate_dev_database(db.get_bind().url)
    from mysite.database.models import (Country, District, Hotel, Region, Tour, TourCategory,
                                        TourProgram, Transport)

    def record(model, lookup, **values):
        item = db.query(model).filter_by(**lookup).first()
        if item is None:
            item = model(**lookup, **values)
            db.add(item)
            db.flush()
        return item

    country = record(Country, {'name': '[DEV] Вымышленная страна'})
    region = record(Region, {'name': '[DEV] Учебный регион'}, country_id=country.id)
    district = record(District, {'name': '[DEV] Учебный район', 'region_id': region.id})
    category = record(TourCategory, {'name': '[DEV] Учебные маршруты'})
    tour = record(
        Tour,
        {'title': '[DEV] Вымышленный поход'},
        price=100,
        description='Вымышленный каталог для локальной разработки. Не реальное предложение.',
        duration_days=2,
        min_people=1,
        max_people=6,
        category_id=category.id,
        country_id=country.id,
    )
    for day in (1, 2):
        record(
            TourProgram,
            {'tour_id': tour.id, 'day_number': day},
            title=f'Учебный день {day}',
            description='Вымышленная программа',
        )
    hotel = record(
        Hotel,
        {'name': '[DEV] Вымышленный гостевой дом'},
        price=50,
        region_id=region.id,
        district_id=district.id,
        stars=3,
    )
    transport = record(Transport, {'name': '[DEV] Учебный автомобиль'}, price=40, seats=5)
    db.commit()
    return {'tour_id': tour.id, 'hotel_id': hotel.id, 'transport_id': transport.id}


def main():
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit('DATABASE_URL is required')
    try:
        validate_dev_database(args.database_url)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    os.environ['DATABASE_URL'] = args.database_url
    from mysite.database.db import SessionLocal

    with SessionLocal() as db:
        result = seed_development(db)
    print(f'Development catalogue ready: {result}')


if __name__ == '__main__':
    main()
