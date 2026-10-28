from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Contact
from mysite.database.schema import ContactInputSchema, ContactOutSchema, ContactUpdateSchema
from mysite.translations.content import Language, localized, update_translations

contact_router = APIRouter(prefix='/contacts', tags=['Contacts'])


@contact_router.post(
    '/', response_model=ContactOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_contact(contact: ContactInputSchema, db: Session = Depends(get_db)):
    contact_db = Contact(**contact.model_dump())

    db.add(contact_db)
    update_translations(contact_db)
    db.commit()
    db.refresh(contact_db)

    return contact_db


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
        raise HTTPException(status_code=404, detail='Байланыш маалыматы табылган жок')

    return localized(contact_db, lang)


@contact_router.put(
    '/{contact_id}/', response_model=ContactOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_contact(contact_id: int, contact: ContactUpdateSchema, db: Session = Depends(get_db)):
    contact_db = db.get(Contact, contact_id)

    if contact_db is None:
        raise HTTPException(status_code=404, detail='Байланыш маалыматы табылган жок')

    data = contact.model_dump(exclude_unset=True)

    if 'is_active' in data and data['is_active'] is None:
        raise HTTPException(status_code=400, detail='is_active бош болбошу керек')

    for key, value in data.items():
        setattr(contact_db, key, value)

    update_translations(contact_db)
    db.commit()
    db.refresh(contact_db)

    return contact_db


@contact_router.delete('/{contact_id}/', dependencies=[Depends(get_current_admin)])
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    contact_db = db.get(Contact, contact_id)

    if contact_db is None:
        raise HTTPException(status_code=404, detail='Байланыш маалыматы табылган жок')

    db.delete(contact_db)
    db.commit()

    return {'message': 'Байланыш маалыматы өчүрүлдү'}
