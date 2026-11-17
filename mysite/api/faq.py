from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import FAQ
from mysite.database.schemas.content import FAQOutSchema
from mysite.translations.content import Language, localized

faq_router = APIRouter(prefix='/faqs', tags=['FAQ'])


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
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(faq_db, lang)
