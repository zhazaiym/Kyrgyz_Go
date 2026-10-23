"""Read-only tools for bounded company information and catalogue queries."""
from copy import deepcopy

from langchain_core.tools import tool
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload

from mysite.chain.prompts import COMPANY_PROFILE
from mysite.database.db import SessionLocal
from mysite.database.models import About, AboutSection, Contact, Tour, Hotel, Transport, FAQ


def _public_text(value, limit):
    if value is None or len(value) <= limit:
        return value
    return value[:limit - 1] + '…'


def _not_demo(column):
    return or_(column.is_(None), and_(
        *(column.notlike(prefix + '%') for prefix in ('ТЕСТ:', 'тест:', 'TEST:', 'test:'))
    ))


def _tour(t, brief=False):
    unit = getattr(getattr(t, 'price_unit', None), 'value', None)
    result = {
        'id': t.id, 'title': t.title,
        'description': _public_text(t.description, 350) if brief else t.description,
        'price': str(t.price) if t.price is not None else None,
        'price_unit': unit, 'currency': 'Уточнить у менеджера',
        'duration_days': t.duration_days, 'min_people': t.min_people, 'max_people': t.max_people,
    }
    if not brief:
        result.update({
            'included': t.included, 'excluded': t.excluded,
            'program': [
                {'day': program.day_number, 'title': program.title, 'description': program.description}
                for program in sorted(t.programs, key=lambda program: program.day_number)
            ],
        })
    return result


@tool
def list_active_tours() -> list[dict]:
    """Read brief active tours (up to 30): price, duration, group limits, short description. Use for initial recommendations, then get_tour_details for program/inclusions. Not live availability."""
    with SessionLocal() as db:
        rows = (db.query(Tour).filter(Tour.is_active.is_(True), _not_demo(Tour.title))
                .order_by(Tour.id).limit(30).all())
        return [_tour(tour, brief=True) for tour in rows]


@tool
def get_tour_details(tour_id: int) -> dict:
    """Read one active tour by known exact numeric ID, with full program and inclusions. Never guess an ID; not live availability."""
    with SessionLocal() as db:
        tour = (db.query(Tour).options(selectinload(Tour.programs))
                .filter(Tour.id == tour_id, Tour.is_active.is_(True), _not_demo(Tour.title)).first())
        return _tour(tour) if tour else {'error': 'Активный тур с таким ID не найден'}


@tool
def get_company_info() -> dict:
    """Read public company profile, active about sections and contacts. Database content overrides supplied profile claims, which are not independently verified. Geography is illustrative, not bookable offers."""
    with SessionLocal() as db:
        about_rows = (db.query(About).filter(About.is_active.is_(True), _not_demo(About.title))
                      .order_by(About.id.desc()).limit(1).all())
        section_rows = (db.query(AboutSection).filter(AboutSection.is_active.is_(True), _not_demo(AboutSection.title))
                        .order_by(AboutSection.order, AboutSection.id).limit(3).all())
        contact_rows = (db.query(Contact).filter(
            Contact.is_active.is_(True), _not_demo(Contact.country),
            _not_demo(Contact.city), _not_demo(Contact.address))
                        .order_by(Contact.id).limit(2).all())
        contact_fields = ('country', 'city', 'phone', 'whatsapp', 'email',
                          'instagram', 'facebook', 'telegram', 'address')
        untruncated_contact_fields = {'phone', 'whatsapp', 'email', 'instagram', 'facebook', 'telegram'}
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
                {'title': _public_text(section.title, 160),
                 'description': _public_text(section.description, 350)}
                for section in section_rows
            ],
            'contacts': contacts,
        }


@tool
def list_active_hotels() -> list[dict]:
    """Read company-listed active accommodation (up to 15). No room availability or booking IDs. Use name/address/price and save client preferences in notes."""
    with SessionLocal() as db:
        rows = db.query(Hotel).filter(Hotel.is_active.is_(True), _not_demo(Hotel.name)).order_by(Hotel.id).limit(15).all()
        return [{'name': hotel.name, 'description': _public_text(hotel.description, 350),
                 'address': hotel.address,
                 'price': str(hotel.price) if hotel.price is not None else None,
                 'price_unit': getattr(hotel.price_unit, 'value', None),
                 'currency': 'Уточнить у менеджера'} for hotel in rows]


@tool
def list_active_transport() -> list[dict]:
    """Read active transport offers (up to 15); not confirmed schedule or seat availability."""
    with SessionLocal() as db:
        rows = db.query(Transport).filter(Transport.is_active.is_(True), _not_demo(Transport.name)).order_by(Transport.id).limit(15).all()
        return [{'name': transport.name, 'description': _public_text(transport.description, 350),
                 'seats': transport.seats,
                 'price': str(transport.price) if transport.price is not None else None,
                 'price_unit': getattr(transport.price_unit, 'value', None),
                 'currency': 'Уточнить у менеджера'} for transport in rows]


@tool
def search_company_faq(question: str) -> list[dict]:
    """Search active company FAQ by relevant phrase. Use for company rules; never invent policies or legal/visa guarantees."""
    words = [word.lower() for word in question.split() if len(word) >= 4][:8]
    with SessionLocal() as db:
        rows = db.query(FAQ).filter(FAQ.is_active.is_(True), _not_demo(FAQ.question)).order_by(FAQ.order).limit(30).all()
        matches = [faq for faq in rows if any(word in (faq.question + ' ' + faq.answer).lower() for word in words)]
        return [{'question': faq.question, 'answer': faq.answer} for faq in (matches or rows[:8])[:8]]


READ_TOOLS = [list_active_tours, get_tour_details, get_company_info, list_active_hotels,
              list_active_transport, search_company_faq]
