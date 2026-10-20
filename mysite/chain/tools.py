"""Read-only LangChain tools querying the EXISTING company SQLAlchemy tables."""
from langchain_core.tools import tool
from sqlalchemy.orm import selectinload
from mysite.database.db import SessionLocal
from mysite.database.models import Tour, Hotel, Transport, FAQ


def _tour(t):
    unit = getattr(getattr(t, 'price_unit', None), 'value', None)
    return {'id': t.id, 'title': t.title, 'description': t.description,
            'price': str(t.price) if t.price is not None else None,
            'price_unit': unit, 'currency': 'Уточнить у менеджера',
            'duration_days': t.duration_days, 'min_people': t.min_people,
            'max_people': t.max_people, 'included': t.included, 'excluded': t.excluded,
            'program': [{'day': p.day_number, 'title': p.title, 'description': p.description}
                        for p in sorted(t.programs, key=lambda p: p.day_number)]}


@tool
def list_active_tours() -> list[dict]:
    """List all active tours from the company DB (up to 30), with prices, duration and program. Use BEFORE recommending tours. Not live availability."""
    with SessionLocal() as db:
        rows = (db.query(Tour).options(selectinload(Tour.programs))
                .filter(Tour.is_active.is_(True)).order_by(Tour.id).limit(30).all())
        return [_tour(t) for t in rows]


@tool
def get_tour_details(tour_id: int) -> dict:
    """Fetch a specific active tour by exact numeric ID from company DB. Never guess an ID."""
    with SessionLocal() as db:
        t = (db.query(Tour).options(selectinload(Tour.programs))
             .filter(Tour.id == tour_id, Tour.is_active.is_(True)).first())
        return _tour(t) if t else {'error': 'Активный тур с таким ID не найден'}


@tool
def list_active_hotels() -> list[dict]:
    """Get company-listed active accommodation from DB; not confirmed room availability (up to 15)."""
    with SessionLocal() as db:
        rows = db.query(Hotel).filter(Hotel.is_active.is_(True)).order_by(Hotel.id).limit(15).all()
        return [{'name': h.name, 'description': h.description, 'address': h.address,
                 'price': str(h.price) if h.price is not None else None,
                 'price_unit': getattr(h.price_unit, 'value', None),
                 'currency': 'Уточнить у менеджера'} for h in rows]


@tool
def list_active_transport() -> list[dict]:
    """Read active transport offers in company DB; not confirmed schedule or seat availability (up to 15)."""
    with SessionLocal() as db:
        rows = db.query(Transport).filter(Transport.is_active.is_(True)).order_by(Transport.id).limit(15).all()
        return [{'name': t.name, 'description': t.description, 'seats': t.seats,
                 'price': str(t.price) if t.price is not None else None,
                 'price_unit': getattr(t.price_unit, 'value', None),
                 'currency': 'Уточнить у менеджера'} for t in rows]


@tool
def search_company_faq(question: str) -> list[dict]:
    """Search company FAQ answers in DB by relevant phrase; return matches or small FAQ list. Never use for invented policies."""
    words = [w.lower() for w in question.split() if len(w) >= 4][:8]
    with SessionLocal() as db:
        rows = db.query(FAQ).filter(FAQ.is_active.is_(True)).order_by(FAQ.order).limit(30).all()
        matches = [f for f in rows if any(w in (f.question + ' ' + f.answer).lower() for w in words)]
        return [{'question': f.question, 'answer': f.answer} for f in (matches or rows[:8])[:8]]


READ_TOOLS = [list_active_tours, get_tour_details, list_active_hotels,
              list_active_transport, search_company_faq]
