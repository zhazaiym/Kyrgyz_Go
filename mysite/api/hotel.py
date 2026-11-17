from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import HotelCardSchema
from mysite.database.db import get_db
from mysite.database.models import Hotel
from mysite.database.schemas.catalogue import HotelOutSchema
from mysite.filters.filter import HotelFilter
from mysite.translations.content import Language, localized

hotel_router = APIRouter(prefix='/hotels', tags=['Hotels'])


@hotel_router.get('/{hotel_id}/', response_model=HotelOutSchema)
def detail_hotel(hotel_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None or not hotel_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(hotel_db, lang)


@hotel_router.get('/', response_model=list[HotelCardSchema])
def list_hotels(
    lang: Language = 'ru',
    filters: HotelFilter = FilterDepends(HotelFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    hotels = filtered_list(
        db=db, model=Hotel, filters=filters, pagination=pagination, lang=lang, active_only=True
    )

    return [localized(hotel, lang) for hotel in hotels]
