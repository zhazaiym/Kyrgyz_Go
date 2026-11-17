from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Contact
from mysite.database.schemas.content import ContactOutSchema
from mysite.translations.content import Language, localized

contact_router = APIRouter(prefix='/contacts', tags=['Contacts'])


@contact_router.get('/', response_model=list[ContactOutSchema])
def list_contacts(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    records = (
        db.query(Contact)
        .filter(Contact.is_active.is_(True))
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return [localized(record, lang) for record in records]


@contact_router.get('/{contact_id}/', response_model=ContactOutSchema)
def detail_contact(contact_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    contact_db = db.get(Contact, contact_id)

    if contact_db is None or not contact_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(contact_db, lang)
