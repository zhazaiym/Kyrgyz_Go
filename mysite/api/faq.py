from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import FAQ
from mysite.database.schema import FAQInputSchema, FAQOutSchema, FAQUpdateSchema
from mysite.translations.content import Language, localized, update_translations

faq_router = APIRouter(prefix='/faqs', tags=['FAQ'])


@faq_router.post('/', response_model=FAQOutSchema, dependencies=[Depends(get_current_admin)])
def create_faq(faq: FAQInputSchema, db: Session = Depends(get_db)):
    faq_db = FAQ(**faq.model_dump())

    db.add(faq_db)
    update_translations(faq_db)
    db.commit()
    db.refresh(faq_db)

    return faq_db


@faq_router.get('/', response_model=list[FAQOutSchema])
def list_faqs(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    records = (
        db.query(FAQ)
        .filter(FAQ.is_active.is_(True))
        .order_by(FAQ.order, FAQ.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return [localized(record, lang) for record in records]


@faq_router.get('/{faq_id}/', response_model=FAQOutSchema)
def detail_faq(faq_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    faq_db = db.get(FAQ, faq_id)

    if faq_db is None or not faq_db.is_active:
        raise HTTPException(status_code=404, detail='Суроо-жооп табылган жок')

    return localized(faq_db, lang)


@faq_router.put(
    '/{faq_id}/', response_model=FAQOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_faq(faq_id: int, faq: FAQUpdateSchema, db: Session = Depends(get_db)):
    faq_db = db.get(FAQ, faq_id)

    if faq_db is None:
        raise HTTPException(status_code=404, detail='Суроо-жооп табылган жок')

    data = faq.model_dump(exclude_unset=True)

    for field in ('question', 'answer'):
        if field in data and not data[field]:
            raise HTTPException(status_code=400, detail=f'{field} бош болбошу керек')

    for field in ('order', 'is_active'):
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f'{field} бош болбошу керек')

    for key, value in data.items():
        setattr(faq_db, key, value)

    update_translations(faq_db)
    db.commit()
    db.refresh(faq_db)

    return faq_db


@faq_router.delete('/{faq_id}/', dependencies=[Depends(get_current_admin)])
def delete_faq(faq_id: int, db: Session = Depends(get_db)):
    faq_db = db.get(FAQ, faq_id)

    if faq_db is None:
        raise HTTPException(status_code=404, detail='Суроо-жооп табылган жок')

    db.delete(faq_db)
    db.commit()

    return {'message': 'Суроо-жооп өчүрүлдү'}
