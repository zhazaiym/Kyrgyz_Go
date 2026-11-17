from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TrekkingCardSchema, TrekkingCatalogueDetailSchema
from mysite.database.db import get_db
from mysite.database.models import Trekking
from mysite.filters.filter import TrekkingFilter
from mysite.translations.content import Language, localized

trekking_router = APIRouter(prefix='/trekkings', tags=['Trekking'])


@trekking_router.get('/{trekking_id}/', response_model=TrekkingCatalogueDetailSchema)
def detail_trekking(trekking_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None or not trekking_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    result = localized(trekking_db, lang)
    result['programs'] = [localized(program, lang) for program in trekking_db.programs]
    return result


@trekking_router.get('/', response_model=list[TrekkingCardSchema])
def list_trekkings(
    lang: Language = 'ru',
    filters: TrekkingFilter = FilterDepends(TrekkingFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    trekkings = filtered_list(
        db=db, model=Trekking, filters=filters, pagination=pagination, lang=lang, active_only=True
    )

    return [localized(trekking, lang) for trekking in trekkings]
