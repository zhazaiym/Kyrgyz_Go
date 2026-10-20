from sqlalchemy.orm import selectinload
from mysite.database.models import Tour, Hotel, Transport, FAQ

def catalog_text(db):
    tours = db.query(Tour).options(selectinload(Tour.programs)).filter(Tour.is_active.is_(True)).limit(30).all()
    hotels = db.query(Hotel).filter(Hotel.is_active.is_(True)).limit(15).all()
    transports = db.query(Transport).filter(Transport.is_active.is_(True)).limit(15).all()
    faqs = db.query(FAQ).filter(FAQ.is_active.is_(True)).order_by(FAQ.order).limit(30).all()
    lines = ['ТУРЫ:']
    for t in tours:
        unit = t.price_unit.value if t.price_unit else 'не указана'
        lines.append(f'ID {t.id}; {t.title}; описание: {t.description or "нет"}; цена {t.price} (единица {unit}, валюту уточнить); дней {t.duration_days}; минимум {t.min_people}; максимум {t.max_people}; включено: {t.included or "не указано"}; не включено: {t.excluded or "не указано"}')
        for p in sorted(t.programs, key=lambda x: x.day_number):
            lines.append(f'День {p.day_number}: {p.title or ""}; {p.description or ""}')
    if not tours: lines.append('Активных туров сейчас нет в базе.')
    lines.append('ЖИЛЬЁ:')
    for h in hotels:
        lines.append(f'{h.name}; {h.description or ""}; {h.address or ""}; цена {h.price}, единица {h.price_unit.value}')
    lines.append('ТРАНСПОРТ:')
    for t in transports:
        lines.append(f'{t.name}; мест {t.seats}; {t.description or ""}; цена {t.price}, единица {t.price_unit.value}')
    lines.append('FAQ:')
    for f in faqs: lines.append(f'Вопрос: {f.question}; ответ: {f.answer}')
    return '\n'.join(lines)[:30000]
