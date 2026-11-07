"""Read-only tools for bounded company information and catalogue queries."""

import re
from copy import deepcopy
from typing import Literal

from langchain_core.tools import tool
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload, selectinload

from ML.prompts import COMPANY_PROFILE

_SEPARATORS = r'[\s‐‑‒–—-]+'
_SQL_SEPARATORS = '[[:space:]‐‑‒–—-]+'
_LAKE_ALIASES = r'(issyk(kul|kol)|ysyk(kul|kol)|ысык(көл|кол|куль)|иссык(көл|кол|куль))'
_DESTINATION_ALIASES = (
    (_LAKE_ALIASES, 'иссыккуль'),
    (r'karakol', 'каракол'),
    (r'(song(kol|kul)|son(kol|kul)|сон(көл|кол|куль))', 'сонкуль'),
)
_UPPER = 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯӨҮҢ'

CATALOGUE_LIMIT = 30
CATALOGUE_KINDS = ('tour', 'helicopter_tour', 'trekking')
CatalogueKind = Literal['tour', 'helicopter_tour', 'trekking']


def _destination_key(value):
    compact = re.sub(_SEPARATORS, '', value.casefold())
    for pattern, canonical in _DESTINATION_ALIASES:
        compact = re.sub(pattern, canonical, compact)
    return compact


def _destination_column(column):
    lowered = func.lower(func.translate(column, _UPPER, _UPPER.lower()))
    compact = func.regexp_replace(lowered, _SQL_SEPARATORS, '', 'g')
    for pattern, canonical in _DESTINATION_ALIASES:
        compact = func.regexp_replace(compact, pattern, canonical, 'g')
    return compact


def SessionLocal():
    from mysite.database.db import SessionLocal as sessions

    return sessions()


def _public_text(value, limit):
    if value is None or len(value) <= limit:
        return value
    return value[: limit - 1] + '…'


def _not_demo(column):
    # Explicit letters keep Cyrillic case handling independent of DB locale.
    return or_(column.is_(None), column.op('!~')('^([Тт][Ее][Сс][Тт]|[Tt][Ee][Ss][Tt]):'))


def _empty_catalogue():
    return {'items': [], 'total': 0, 'has_more': False}


def _invalid_arguments(error):
    return (
        'error: неверные параметры инструмента; kind — tour, helicopter_tour или trekking, '
        'числа — положительные целые'
    )


def _text_number(value):
    return str(value) if value is not None else None


def _program(rows):
    return [
        {'day': row.day_number, 'title': row.title, 'description': row.description}
        for row in sorted(rows, key=lambda row: row.day_number)
    ]


def _base_item(kind, record, brief):
    return {
        'kind': kind,
        'id': record.id,
        'title': record.title,
        'description': _public_text(record.description, 350) if brief else record.description,
        'price': _text_number(record.price),
        'price_unit': getattr(record.price_unit, 'value', None),
        'currency': 'Уточнить у менеджера',
    }


def _tour_item(tour, brief=True):
    item = _base_item('tour', tour, brief)
    item.update(
        {
            'country': tour.country.name if tour.country else None,
            'duration_days': tour.duration_days,
            'min_people': tour.min_people,
            'max_people': tour.max_people,
        }
    )
    if not brief:
        item.update(
            {
                'included': tour.included,
                'excluded': tour.excluded,
                'program': _program(tour.programs),
            }
        )
    return item


def _helicopter_item(flight, brief=True):
    item = _base_item('helicopter_tour', flight, brief)
    item.update(
        {
            'destination': flight.destination,
            'departure_location': flight.departure_location,
            'duration_minutes': flight.duration_minutes,
            'max_passengers': flight.max_passengers,
        }
    )
    if not brief:
        item.update({'instruction': flight.instruction, 'included': flight.included})
    return item


def _trekking_item(trek, brief=True):
    item = _base_item('trekking', trek, brief)
    item.update(
        {
            'route': _public_text(trek.route, 350) if brief else trek.route,
            'duration_days': trek.duration_days,
            'duration_hours': trek.duration_hours,
            'difficulty': trek.difficulty,
            'distance_km': _text_number(trek.distance_km),
            'min_people': trek.min_people,
            'max_people': trek.max_people,
        }
    )
    if not brief:
        item.update(
            {
                'included': trek.included,
                'requirements': trek.requirements,
                'max_altitude': trek.max_altitude,
                'program': _program(trek.programs),
            }
        )
    return item


def _catalogue_kinds():
    from mysite.database.models import Country, HelicopterTour, Tour, Trekking

    return {
        'tour': (Tour, _tour_item, (Tour.title, Tour.description, Country.name)),
        'helicopter_tour': (
            HelicopterTour,
            _helicopter_item,
            (
                HelicopterTour.title,
                HelicopterTour.description,
                HelicopterTour.destination,
                HelicopterTour.departure_location,
            ),
        ),
        'trekking': (
            Trekking,
            _trekking_item,
            (Trekking.title, Trekking.description, Trekking.route),
        ),
    }


def _catalogue_query(db, kind, model):
    query = db.query(model).filter(model.is_active.is_(True), _not_demo(model.title))
    if kind == 'tour':
        query = query.outerjoin(model.country).options(joinedload(model.country))
    return query


def _capacity_filter(kind, model, people_count):
    if kind == 'helicopter_tour':
        return or_(model.max_passengers.is_(None), model.max_passengers >= people_count)
    return and_(
        or_(model.min_people.is_(None), model.min_people <= people_count),
        or_(model.max_people.is_(None), model.max_people >= people_count),
    )


def _destination_filter(columns, destination):
    keyword = _destination_key(destination)
    keyword = keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    pattern = f'%{keyword}%'
    return or_(*(_destination_column(column).like(pattern, escape='\\') for column in columns))


@tool
def search_catalogue(
    kind: CatalogueKind | None = None,
    destination: str | None = None,
    people_count: int | None = None,
    duration_days: int | None = None,
    min_duration_days: int | None = None,
    max_duration_days: int | None = None,
) -> dict:
    """Search the active catalogue: tours (tour), helicopter tours (helicopter_tour) and trekking. Omit kind for all kinds and omit filters for initial recommendations. destination matches names, descriptions and places. duration_days is exact; min/max_duration_days set a flexible range (up to a week: max_duration_days=7). Day filters do not apply to helicopter tours, which last minutes. Returns items (kind + id identify a record), total and has_more. Not live availability."""
    numbers = (people_count, duration_days, min_duration_days, max_duration_days)
    if any(value is not None and value <= 0 for value in numbers):
        return _empty_catalogue()
    if (
        min_duration_days is not None
        and max_duration_days is not None
        and min_duration_days > max_duration_days
    ):
        return _empty_catalogue()

    kinds = _catalogue_kinds()
    items, total = [], 0
    with SessionLocal() as db:
        for name in [kind] if kind else CATALOGUE_KINDS:
            model, serialize, columns = kinds[name]
            query = _catalogue_query(db, name, model)
            if destination and destination.strip():
                query = query.filter(_destination_filter(columns, destination.strip()))
            if people_count is not None:
                query = query.filter(_capacity_filter(name, model, people_count))
            if name != 'helicopter_tour':
                if duration_days is not None:
                    query = query.filter(model.duration_days == duration_days)
                if min_duration_days is not None:
                    query = query.filter(model.duration_days >= min_duration_days)
                if max_duration_days is not None:
                    query = query.filter(model.duration_days <= max_duration_days)
            rows = query.order_by(model.id).limit(CATALOGUE_LIMIT + 1).all()
            room = CATALOGUE_LIMIT - len(items)
            items.extend(serialize(row) for row in rows[:room])
            total += len(rows) if len(rows) <= CATALOGUE_LIMIT else query.count()
    return {'items': items, 'total': total, 'has_more': total > len(items)}


search_catalogue.handle_validation_error = _invalid_arguments


@tool
def get_catalogue_item(kind: CatalogueKind, id: int) -> dict:
    """Read one active catalogue record by kind and exact id from search_catalogue: tour program and inclusions; helicopter tour destination, departure, instruction and inclusions; trekking route, requirements, altitude and program. Never guess an id; not live availability."""
    model, serialize, _ = _catalogue_kinds()[kind]
    with SessionLocal() as db:
        query = _catalogue_query(db, kind, model)
        if kind != 'helicopter_tour':
            query = query.options(selectinload(model.programs))
        record = query.filter(model.id == id).first()
        if record is None:
            return {'error': 'Активная запись каталога с таким kind и id не найдена'}
        return serialize(record, brief=False)


get_catalogue_item.handle_validation_error = _invalid_arguments


@tool
def get_company_info() -> dict:
    """Read public company profile, active about sections and contacts. Database content overrides supplied profile claims, which are not independently verified. Geography is illustrative, not bookable offers."""
    from mysite.database.models import About, AboutSection, Contact

    with SessionLocal() as db:
        about_rows = (
            db.query(About)
            .filter(About.is_active.is_(True), _not_demo(About.title))
            .order_by(About.id.desc())
            .limit(1)
            .all()
        )
        section_rows = (
            db.query(AboutSection)
            .filter(AboutSection.is_active.is_(True), _not_demo(AboutSection.title))
            .order_by(AboutSection.order, AboutSection.id)
            .limit(3)
            .all()
        )
        contact_rows = (
            db.query(Contact)
            .filter(
                Contact.is_active.is_(True),
                _not_demo(Contact.country),
                _not_demo(Contact.city),
                _not_demo(Contact.address),
            )
            .order_by(Contact.id)
            .limit(2)
            .all()
        )
        contact_fields = (
            'country',
            'city',
            'phone',
            'whatsapp',
            'email',
            'instagram',
            'facebook',
            'telegram',
            'address',
        )
        untruncated_contact_fields = {
            'phone',
            'whatsapp',
            'email',
            'instagram',
            'facebook',
            'telegram',
        }
        contacts = []
        for contact in contact_rows:
            public_contact = {}
            for field in contact_fields:
                value = getattr(contact, field)
                if value is None:
                    continue
                if 'example.invalid' in value.casefold():
                    continue
                if field in untruncated_contact_fields and len(value) > 160:
                    continue
                public_contact[field] = _public_text(value, 160)
            if public_contact:
                contacts.append(public_contact)
        return {
            'approved_profile': deepcopy(COMPANY_PROFILE),
            'about': [
                {
                    'title': _public_text(about.title, 160),
                    'description': _public_text(about.description, 600),
                    'experience_years': about.experience_years,
                    'travelers_count': about.travelers_count,
                    'branches_count': about.branches_count,
                    'destinations_count': about.destinations_count,
                    'routes_count': about.routes_count,
                }
                for about in about_rows
            ],
            'sections': [
                {
                    'title': _public_text(section.title, 160),
                    'description': _public_text(section.description, 350),
                }
                for section in section_rows
            ],
            'contacts': contacts,
        }


@tool
def list_active_hotels() -> list[dict]:
    """Read company-listed active accommodation (up to 15). No room availability or booking IDs. Use name/address/price and save client preferences in notes."""
    from mysite.database.models import Hotel

    with SessionLocal() as db:
        rows = (
            db.query(Hotel)
            .filter(Hotel.is_active.is_(True), _not_demo(Hotel.name))
            .order_by(Hotel.id)
            .limit(15)
            .all()
        )
        return [
            {
                'name': hotel.name,
                'description': _public_text(hotel.description, 350),
                'address': hotel.address,
                'price': str(hotel.price) if hotel.price is not None else None,
                'price_unit': getattr(hotel.price_unit, 'value', None),
                'currency': 'Уточнить у менеджера',
            }
            for hotel in rows
        ]


@tool
def list_active_transport() -> list[dict]:
    """Read active transport offers (up to 15); not confirmed schedule or seat availability."""
    from mysite.database.models import Transport

    with SessionLocal() as db:
        rows = (
            db.query(Transport)
            .filter(Transport.is_active.is_(True), _not_demo(Transport.name))
            .order_by(Transport.id)
            .limit(15)
            .all()
        )
        return [
            {
                'name': transport.name,
                'description': _public_text(transport.description, 350),
                'seats': transport.seats,
                'price': str(transport.price) if transport.price is not None else None,
                'price_unit': getattr(transport.price_unit, 'value', None),
                'currency': 'Уточнить у менеджера',
            }
            for transport in rows
        ]


@tool
def search_company_faq(question: str) -> list[dict]:
    """Search active company FAQ by relevant phrase. Use for company rules; never invent policies or legal/visa guarantees."""
    from mysite.database.models import FAQ

    words = [word.lower() for word in question.split() if len(word) >= 4][:8]
    if not words:
        return []
    with SessionLocal() as db:
        rows = (
            db.query(FAQ)
            .filter(FAQ.is_active.is_(True), _not_demo(FAQ.question))
            .order_by(FAQ.order)
            .limit(30)
            .all()
        )
        matches = [
            faq
            for faq in rows
            if any(word in (faq.question + ' ' + faq.answer).lower() for word in words)
        ]
        return [{'question': faq.question, 'answer': faq.answer} for faq in matches[:8]]


READ_TOOLS = [
    search_catalogue,
    get_catalogue_item,
    get_company_info,
    list_active_hotels,
    list_active_transport,
    search_company_faq,
]
