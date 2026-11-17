from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.db import get_db
from mysite.database.models import Region
from mysite.database.schemas.catalogue import RegionOutSchema
from mysite.filters.filter import RegionFilter
from mysite.translations.content import Language, localized

region_router = APIRouter(prefix='/regions', tags=['Regions'])


@region_router.get('/{region_id}/', response_model=RegionOutSchema)
def detail_region(region_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(region_db, lang)


@region_router.get('/', response_model=list[RegionOutSchema])
def list_regions(
    lang: Language = 'ru',
    filters: RegionFilter = FilterDepends(RegionFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    regions = filtered_list(db=db, model=Region, filters=filters, pagination=pagination, lang=lang)

    return [localized(region, lang) for region in regions]
