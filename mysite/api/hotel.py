from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.deletion_guards import protect_selected_item
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import HotelCardSchema
from mysite.database.db import get_db
from mysite.database.models import District, Hotel, Region
from mysite.database.schema import HotelInputSchema, HotelOutSchema, HotelUpdateSchema
from mysite.filters.filter import HotelFilter
from mysite.translations.content import Language, localized, update_translations

hotel_router = APIRouter(prefix='/hotels', tags=['Hotels'])


def check_location(db, region_id, district_id):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(status_code=404, detail='Область табылган жок')

    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(status_code=404, detail='Район табылган жок')

    if district_db.region_id != region_id:
        raise HTTPException(status_code=400, detail='Район бул областька тиешелүү эмес')


@hotel_router.post('/', response_model=HotelOutSchema, dependencies=[Depends(get_current_admin)])
def create_hotel(hotel: HotelInputSchema, db: Session = Depends(get_db)):
    check_location(db, hotel.region_id, hotel.district_id)

    hotel_db = Hotel(**hotel.model_dump())

    db.add(hotel_db)
    update_translations(hotel_db)
    db.commit()
    db.refresh(hotel_db)

    return hotel_db


@hotel_router.get(
    '/{hotel_id}/', response_model=HotelOutSchema, dependencies=[Depends(current_client)]
)
def detail_hotel(hotel_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None or not hotel_db.is_active:
        raise HTTPException(status_code=404, detail='Мейманкана табылган жок')

    return localized(hotel_db, lang)


@hotel_router.put(
    '/{hotel_id}/', response_model=HotelOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_hotel(hotel_id: int, hotel: HotelUpdateSchema, db: Session = Depends(get_db)):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None:
        raise HTTPException(status_code=404, detail='Мейманкана табылган жок')

    data = hotel.model_dump(exclude_unset=True)

    region_id = data.get('region_id', hotel_db.region_id)

    district_id = data.get('district_id', hotel_db.district_id)

    if region_id is None or district_id is None:
        raise HTTPException(status_code=400, detail='Область жана район милдеттүү')

    check_location(db, region_id, district_id)

    for key, value in data.items():
        setattr(hotel_db, key, value)

    update_translations(hotel_db)
    db.commit()
    db.refresh(hotel_db)

    return hotel_db


@hotel_router.delete('/{hotel_id}/', dependencies=[Depends(get_current_admin)])
def delete_hotel(hotel_id: int, db: Session = Depends(get_db)):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None:
        raise HTTPException(status_code=404, detail='Мейманкана табылган жок')

    protect_selected_item(db, Hotel, hotel_id)
    db.delete(hotel_db)
    db.commit()

    return {'message': 'Мейманкана өчүрүлдү'}


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
