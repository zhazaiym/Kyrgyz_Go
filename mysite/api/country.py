from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Country, Tour
from mysite.database.schema import CountryInputSchema, CountryOutSchema, CountryUpdateSchema
from mysite.translations.content import Language, localized, update_translations

country_router = APIRouter(prefix='/countries', tags=['Countries'])


@country_router.post(
    '/', response_model=CountryOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_country(country: CountryInputSchema, db: Session = Depends(get_db)):
    country_db = Country(name=country.name)

    db.add(country_db)
    update_translations(country_db)
    db.commit()
    db.refresh(country_db)

    return country_db


@country_router.get('/', response_model=list[CountryOutSchema])
def list_countries(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    return [
        localized(record, lang)
        for record in db.query(Country).offset(pagination.offset).limit(pagination.limit).all()
    ]


@country_router.get('/{country_id}/', response_model=CountryOutSchema)
def detail_country(country_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    country_db = db.get(Country, country_id)

    if country_db is None:
        raise HTTPException(status_code=404, detail='Мамлекет табылган жок')

    return localized(country_db, lang)


@country_router.put(
    '/{country_id}/', response_model=CountryOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_country(country_id: int, country: CountryUpdateSchema, db: Session = Depends(get_db)):
    country_db = db.get(Country, country_id)

    if country_db is None:
        raise HTTPException(status_code=404, detail='Мамлекет табылган жок')

    data = country.model_dump(exclude_unset=True)

    if 'name' in data:
        if not data['name'] or not data['name'].strip():
            raise HTTPException(status_code=400, detail='Мамлекеттин аты бош болбошу керек')

        country_db.name = data['name']

    update_translations(country_db)
    db.commit()
    db.refresh(country_db)

    return country_db


@country_router.delete('/{country_id}/', dependencies=[Depends(get_current_admin)])
def delete_country(country_id: int, db: Session = Depends(get_db)):
    country_db = db.get(Country, country_id, with_for_update=True)

    if country_db is None:
        raise HTTPException(status_code=404, detail='Мамлекет табылган жок')

    if country_db.regions:
        raise HTTPException(status_code=400, detail='Бул мамлекетке областтар байланышкан')
    if db.query(Tour.id).filter(Tour.country_id == country_id).first():
        raise HTTPException(409, 'Country is used by tours')

    db.delete(country_db)
    db.commit()

    return {'message': 'Мамлекет өчүрүлдү'}
