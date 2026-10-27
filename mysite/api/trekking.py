from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TrekkingCardSchema, TrekkingCatalogueDetailSchema
from mysite.database.db import get_db
from mysite.database.models import Trekking
from mysite.database.schema import TrekkingInputSchema, TrekkingOutSchema, TrekkingUpdateSchema
from mysite.filters.filter import TrekkingFilter
from mysite.translations.content import Language, localized, update_translations

trekking_router = APIRouter(prefix='/trekkings', tags=['Trekking'])


@trekking_router.post(
    '/', response_model=TrekkingOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_trekking(trekking: TrekkingInputSchema, db: Session = Depends(get_db)):
    trekking_db = Trekking(**trekking.model_dump())

    db.add(trekking_db)
    update_translations(trekking_db)
    db.commit()
    db.refresh(trekking_db)

    return trekking_db


@trekking_router.get(
    '/{trekking_id}/',
    response_model=TrekkingCatalogueDetailSchema,
    dependencies=[Depends(current_client)],
)
def detail_trekking(trekking_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None or not trekking_db.is_active:
        raise HTTPException(status_code=404, detail='Треккинг табылган жок')

    return localized(trekking_db, lang)


@trekking_router.put(
    '/{trekking_id}/', response_model=TrekkingOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_trekking(
    trekking_id: int, trekking: TrekkingUpdateSchema, db: Session = Depends(get_db)
):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None:
        raise HTTPException(status_code=404, detail='Треккинг табылган жок')

    data = trekking.model_dump(exclude_unset=True)

    for field in ('title', 'price', 'price_unit', 'is_active'):
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f'{field} бош болбошу керек')

    for key, value in data.items():
        setattr(trekking_db, key, value)

    update_translations(trekking_db)
    db.commit()
    db.refresh(trekking_db)

    return trekking_db


@trekking_router.delete('/{trekking_id}/', dependencies=[Depends(get_current_admin)])
def delete_trekking(trekking_id: int, db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None:
        raise HTTPException(status_code=404, detail='Треккинг табылган жок')

    db.delete(trekking_db)
    db.commit()

    return {'message': 'Треккинг өчүрүлдү'}


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
