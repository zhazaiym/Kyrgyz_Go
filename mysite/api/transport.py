from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TransportCardSchema
from mysite.database.db import get_db
from mysite.database.models import Transport
from mysite.database.schemas.catalogue import TransportOutSchema
from mysite.filters.filter import TransportFilter
from mysite.translations.content import Language, localized

transport_router = APIRouter(prefix='/transports', tags=['Transports'])


@transport_router.get('/{transport_id}/', response_model=TransportOutSchema)
def detail_transport(transport_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None or not transport_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(transport_db, lang)


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
