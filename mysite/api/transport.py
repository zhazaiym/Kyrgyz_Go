from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.deletion_guards import protect_selected_item
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TransportCardSchema
from mysite.database.db import get_db
from mysite.database.models import Transport
from mysite.database.schema import TransportInputSchema, TransportOutSchema, TransportUpdateSchema
from mysite.filters.filter import TransportFilter
from mysite.translations.content import Language, localized, update_translations

transport_router = APIRouter(prefix='/transports', tags=['Transports'])


@transport_router.post(
    '/', response_model=TransportOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_transport(transport: TransportInputSchema, db: Session = Depends(get_db)):
    transport_db = Transport(**transport.model_dump())

    db.add(transport_db)
    update_translations(transport_db)
    db.commit()
    db.refresh(transport_db)

    return transport_db


@transport_router.get(
    '/{transport_id}/', response_model=TransportOutSchema, dependencies=[Depends(current_client)]
)
def detail_transport(transport_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None or not transport_db.is_active:
        raise HTTPException(status_code=404, detail='Транспорт табылган жок')

    return localized(transport_db, lang)


@transport_router.put(
    '/{transport_id}/', response_model=TransportOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_transport(
    transport_id: int, transport: TransportUpdateSchema, db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None:
        raise HTTPException(status_code=404, detail='Транспорт табылган жок')

    data = transport.model_dump(exclude_unset=True)

    for field in ('name', 'seats', 'price'):
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f'{field} бош болбошу керек')

    for key, value in data.items():
        setattr(transport_db, key, value)

    update_translations(transport_db)
    db.commit()
    db.refresh(transport_db)

    return transport_db


@transport_router.delete('/{transport_id}/', dependencies=[Depends(get_current_admin)])
def delete_transport(transport_id: int, db: Session = Depends(get_db)):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None:
        raise HTTPException(status_code=404, detail='Транспорт табылган жок')

    protect_selected_item(db, Transport, transport_id)
    db.delete(transport_db)
    db.commit()

    return {'message': 'Транспорт өчүрүлдү'}


@transport_router.get('/', response_model=list[TransportCardSchema])
def list_transports(
    lang: Language = 'ru',
    filters: TransportFilter = FilterDepends(TransportFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    transports = filtered_list(
        db=db, model=Transport, filters=filters, pagination=pagination, lang=lang, active_only=True
    )

    return [localized(transport, lang) for transport in transports]
