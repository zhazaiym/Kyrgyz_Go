from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Country
from mysite.database.schemas.catalogue import CountryOutSchema
from mysite.translations.content import Language, localized

country_router = APIRouter(prefix='/countries', tags=['Countries'])


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
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(country_db, lang)
