from decimal import Decimal
from uuid import uuid4

from ML.tools import search_tours
from mysite.database.db import SessionLocal
from mysite.database.models import Country, Tour


def test_search_tours_database():
    unique = uuid4().hex[:10]

    with SessionLocal() as db:
        country = Country(name=f'Kyrgyz Republic {unique}')
        db.add(country)
        db.flush()
        tours = [
            Tour(
                title=f'Issyk Kul {unique}',
                description='Lake tour',
                price=Decimal('5000'),
                duration_days=3,
                min_people=1,
                max_people=5,
                is_active=True,
                country_id=country.id,
            ),
            Tour(
                title=f'Alay {unique}',
                description='Mountain tour',
                price=Decimal('8000'),
                duration_days=5,
                min_people=2,
                max_people=10,
                is_active=True,
            ),
            Tour(
                title=f'Hidden {unique}',
                description='Inactive tour',
                price=Decimal('1000'),
                duration_days=3,
                min_people=1,
                max_people=5,
                is_active=False,
            ),
        ]

        db.add_all(tours)
        db.commit()

        try:
            for tour in tours:
                db.refresh(tour)

            issyk_id = tours[0].id
            alay_id = tours[1].id
            hidden_id = tours[2].id

            result = search_tours.invoke({'destination': f'Issyk Kul {unique}'})
            assert issyk_id in [t['id'] for t in result]

            country_result = search_tours.invoke({'destination': country.name})
            matching_tour = next(t for t in country_result if t['id'] == issyk_id)
            assert matching_tour['country'] == country.name

            result = search_tours.invoke({'destination': unique, 'people_count': 8})
            ids = [t['id'] for t in result]

            assert alay_id in ids
            assert issyk_id not in ids

            result = search_tours.invoke({'destination': unique, 'duration_days': 3})
            ids = [t['id'] for t in result]

            assert issyk_id in ids
            assert alay_id not in ids
            assert hidden_id not in ids

        finally:
            for tour in tours:
                db.delete(tour)
            db.delete(country)
            db.commit()
