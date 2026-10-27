import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from mysite.chain import tools
from mysite.database.db import Base
from mysite.database.models import About, AboutSection, Contact, Tour, TourProgram
from tests.postgres_support import temporary_database


@pytest.fixture
def company_database(monkeypatch):
    with temporary_database() as url:
        engine = create_engine(url)
        try:
            Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine)
            monkeypatch.setattr(tools, 'SessionLocal', sessions)
            yield sessions, engine
        finally:
            engine.dispose()


def test_company_info_uses_active_database_content_and_public_contact_fields(company_database):
    sessions, _ = company_database
    with sessions() as db:
        db.add_all(
            [
                About(
                    title='Current company profile',
                    description='Updated company services',
                    experience_years=9,
                    travelers_count=31000,
                    branches_count=4,
                    destinations_count=24,
                    routes_count=120,
                    is_active=True,
                ),
                About(title='Inactive company profile', description='Do not show', is_active=False),
                AboutSection(title='Later section', description='Second public section', order=2),
                AboutSection(title='First section', description='First public section', order=1),
                AboutSection(title='Hidden section', description='Private draft', is_active=False),
                Contact(
                    country='Кыргызстан',
                    city='Бишкек',
                    phone='+996 700 123456',
                    whatsapp='https://wa.me/996700123456',
                    email='office@example.test',
                    instagram='https://instagram.example.test/company',
                    address='Public office address',
                    qr_code='internal-qr-file',
                    translations={'private': 'translation payload'},
                ),
                Contact(phone='inactive-phone', email='hidden@example.test', is_active=False),
            ]
        )
        db.flush()
        # Insert listeners assign ID order; exercise sorting with edited order.
        db.query(AboutSection).filter_by(title='First section').update({'order': 1})
        db.query(AboutSection).filter_by(title='Later section').update({'order': 2})
        db.commit()

    result = tools.get_company_info.invoke({})

    assert result['about'] == [
        {
            'title': 'Current company profile',
            'description': 'Updated company services',
            'experience_years': 9,
            'travelers_count': 31000,
            'branches_count': 4,
            'destinations_count': 24,
            'routes_count': 120,
        }
    ]
    assert [section['title'] for section in result['sections']] == [
        'First section',
        'Later section',
    ]
    assert len(result['contacts']) == 1
    assert result['contacts'][0]['phone'] == '+996 700 123456'
    assert result['contacts'][0]['email'] == 'office@example.test'
    assert result['contacts'][0]['address'] == 'Public office address'
    assert set(result['contacts'][0]) <= {
        'country',
        'city',
        'phone',
        'whatsapp',
        'email',
        'instagram',
        'facebook',
        'telegram',
        'address',
    }
    serialized = json.dumps(result, ensure_ascii=False)
    assert 'Inactive company profile' not in serialized
    assert 'Hidden section' not in serialized
    assert 'inactive-phone' not in serialized
    assert 'internal-qr-file' not in serialized
    assert 'translation payload' not in serialized
    assert result['approved_profile']['source'] == 'user_provided_not_independently_verified'
    assert 'get_company_info' in {tool.name for tool in tools.READ_TOOLS}


def test_company_info_bounds_large_text_and_does_not_invent_contact_fallbacks(company_database):
    sessions, _ = company_database
    with sessions() as db:
        db.add_all(
            [
                About(title=f'Profile {index}', description='Long public description ' * 1000)
                for index in range(4)
            ]
        )
        db.add_all(
            [
                AboutSection(
                    title=f'Section {index}', description='Long public section ' * 1000, order=index
                )
                for index in range(12)
            ]
        )
        db.add_all(
            [
                Contact(city=f'Office {index}', address='Long public address ' * 25)
                for index in range(10)
            ]
        )
        db.commit()

    result = tools.get_company_info.invoke({})

    assert len(result['about']) <= 1
    assert len(result['sections']) <= 3
    assert len(result['contacts']) <= 2
    assert all(len(item['description']) <= 600 for item in result['about'])
    assert all(len(item['description']) <= 350 for item in result['sections'])
    assert all(len(item['address']) <= 160 for item in result['contacts'])
    assert all(not item.get('phone') and not item.get('email') for item in result['contacts'])
    assert len(json.dumps(result, ensure_ascii=False)) < 6000


def test_company_info_excludes_explicit_demo_records_and_placeholder_contacts(company_database):
    sessions, _ = company_database
    with sessions() as db:
        db.add_all(
            [
                About(title='Public company record', description='Current public information'),
                About(
                    title='ТЕСТ: Demonstration company',
                    description='Never present as company history',
                ),
                AboutSection(title='TEST: Demonstration section', description='Synthetic section'),
                AboutSection(
                    title='Actual public section', description='Real published description'
                ),
                Contact(
                    country='ТЕСТ: Кыргызстан', city='Synthetic office', phone='+1 202-555-0100'
                ),
                Contact(
                    city='Public office',
                    phone='+996 700 654321',
                    email='placeholder@example.invalid',
                    instagram='https://example.invalid/instagram',
                ),
            ]
        )
        db.commit()

    result = tools.get_company_info.invoke({})

    assert [about['title'] for about in result['about']] == ['Public company record']
    assert [section['title'] for section in result['sections']] == ['Actual public section']
    assert result['contacts'] == [{'city': 'Public office', 'phone': '+996 700 654321'}]


def test_tour_list_is_brief_and_details_keep_the_existing_program(company_database):
    sessions, engine = company_database
    with sessions() as db:
        active = Tour(
            title='Bounded catalogue tour',
            description='Tour description ' * 100,
            price='125.00',
            duration_days=2,
            included='Guide included',
            excluded='Lunch excluded',
        )
        hidden = Tour(title='Inactive catalogue tour', price='99.00', is_active=False)
        db.add_all([active, hidden])
        db.flush()
        db.add(
            TourProgram(
                tour_id=active.id, day_number=1, title='Real first day', description='Day details'
            )
        )
        tour_id = active.id
        hidden_id = hidden.id
        db.commit()

    statements = []

    def capture_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', capture_statement)
    brief = tools.list_active_tours.invoke({})
    event.remove(engine, 'before_cursor_execute', capture_statement)

    assert len(brief) == 1
    assert brief[0]['id'] == tour_id
    assert brief[0]['title'] == 'Bounded catalogue tour'
    assert len(brief[0]['description']) <= 350
    assert not {'included', 'excluded', 'program'} & brief[0].keys()
    assert len(statements) == 1
    assert 'tour_programs' not in statements[0].lower()

    detail = tools.get_tour_details.invoke({'tour_id': tour_id})
    assert detail['included'] == 'Guide included'
    assert detail['excluded'] == 'Lunch excluded'
    assert detail['program'] == [
        {'day': 1, 'title': 'Real first day', 'description': 'Day details'}
    ]
    assert len(detail['description']) > len(brief[0]['description'])
    assert 'error' in tools.get_tour_details.invoke({'tour_id': hidden_id})


def test_demonstration_tours_do_not_consume_real_offer_limit(company_database, monkeypatch):
    from mysite.chain import agent

    sessions, _ = company_database
    with sessions() as db:
        demonstrations = [Tour(title=f'ТЕСТ: Example {index}', price=10) for index in range(31)]
        real = Tour(title='Published real tour', price=100)
        db.add_all(demonstrations + [real])
        db.commit()
        demo_id = demonstrations[0].id
        real_id = real.id
    assert [tour['id'] for tour in tools.list_active_tours.invoke({})] == [real_id]
    assert 'error' in tools.get_tour_details.invoke({'tour_id': demo_id})
    monkeypatch.setattr(agent, 'SessionLocal', sessions)
    assert agent.active_tour_ids() == [real_id]
