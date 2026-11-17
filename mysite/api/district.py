from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.db import get_db
from mysite.database.models import District
from mysite.database.schemas.catalogue import DistrictOutSchema
from mysite.filters.filter import DistrictFilter
from mysite.translations.content import Language, localized

district_router = APIRouter(prefix='/districts', tags=['Districts'])


@district_router.get('/{district_id}/', response_model=DistrictOutSchema)
def detail_district(district_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(district_db, lang)


@district_router.get('/', response_model=list[DistrictOutSchema])
def list_districts(
    lang: Language = 'ru',
    filters: DistrictFilter = FilterDepends(DistrictFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    districts = filtered_list(
        db=db, model=District, filters=filters, pagination=pagination, lang=lang
    )

    return [localized(district, lang) for district in districts]
