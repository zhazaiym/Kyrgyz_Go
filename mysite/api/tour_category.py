from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import TourCategory
from mysite.database.schemas.catalogue import TourCategoryOutSchema
from mysite.translations.content import Language, localized

category_router = APIRouter(prefix='/tour-categories', tags=['Tour Categories'])


@category_router.get('/', response_model=list[TourCategoryOutSchema])
def list_category(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    return [
        localized(record, lang)
        for record in db.query(TourCategory).offset(pagination.offset).limit(pagination.limit).all()
    ]


@category_router.get('/{category_id}/', response_model=TourCategoryOutSchema)
def detail_category(category_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(category_db, lang)
