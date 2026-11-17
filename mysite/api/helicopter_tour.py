from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import (HelicopterCatalogueDetailSchema,
                                              HelicopterTourCardSchema)
from mysite.database.db import get_db
from mysite.database.models import HelicopterTour
from mysite.filters.filter import HelicopterTourFilter
from mysite.translations.content import Language, localized

helicopter_tour_router = APIRouter(prefix='/helicopter-tours', tags=['Helicopter Tours'])


@helicopter_tour_router.get('/{helicopter_id}/', response_model=HelicopterCatalogueDetailSchema)
def detail_helicopter_tour(
    helicopter_id: int, lang: Language = 'ru', db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_id)

    if helicopter_db is None or not helicopter_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(helicopter_db, lang)


@helicopter_tour_router.get('/', response_model=list[HelicopterTourCardSchema])
def list_helicopter_tours(
    lang: Language = 'ru',
    filters: HelicopterTourFilter = FilterDepends(HelicopterTourFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    helicopters = filtered_list(
        db=db,
        model=HelicopterTour,
        filters=filters,
        pagination=pagination,
        lang=lang,
        active_only=True,
    )

    return [localized(helicopter, lang) for helicopter in helicopters]
