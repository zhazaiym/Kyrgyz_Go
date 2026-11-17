from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import About
from mysite.database.schemas.content import AboutOutSchema
from mysite.translations.content import Language, localized

about_router = APIRouter(prefix='/abouts', tags=['About'])


@about_router.get('/', response_model=list[AboutOutSchema])
def list_about(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    records = (
        db.query(About)
        .filter(About.is_active.is_(True))
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return [localized(record, lang) for record in records]


@about_router.get('/{about_id}/', response_model=AboutOutSchema)
def detail_about(about_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db or not about_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    return localized(about_db, lang)
