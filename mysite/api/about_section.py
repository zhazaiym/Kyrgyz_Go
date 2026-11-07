from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import AboutSection
from mysite.database.schemas.content import (AboutSectionInputSchema, AboutSectionOutSchema,
                                             AboutSectionUpdateSchema)
from mysite.translations.content import Language, localized, update_translations

about_section_router = APIRouter(prefix='/about-sections', tags=['About Sections'])


@about_section_router.post(
    '/',
    response_model=AboutSectionOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_about_section(data: AboutSectionInputSchema, db: Session = Depends(get_db)):
    section_db = AboutSection(**data.model_dump())
    db.add(section_db)
    update_translations(section_db)
    db.commit()
    db.refresh(section_db)
    return section_db


@about_section_router.get('/', response_model=list[AboutSectionOutSchema])
def list_about_sections(
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    records = (
        db.query(AboutSection)
        .filter(AboutSection.is_active.is_(True))
        .order_by(AboutSection.order, AboutSection.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return [localized(record, lang) for record in records]


@about_section_router.get('/{section_id}/', response_model=AboutSectionOutSchema)
def detail_about_section(section_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    section_db = db.get(AboutSection, section_id)
    if not section_db or not section_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    return localized(section_db, lang)


@about_section_router.put(
    '/{section_id}/',
    response_model=AboutSectionOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_about_section(
    section_id: int, data: AboutSectionUpdateSchema, db: Session = Depends(get_db)
):
    section_db = db.get(AboutSection, section_id)
    if not section_db:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(section_db, key, value)

    update_translations(section_db)
    db.commit()
    db.refresh(section_db)
    return section_db


@about_section_router.delete(
    '/{section_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_about_section(section_id: int, db: Session = Depends(get_db)):
    section_db = db.get(AboutSection, section_id)
    if not section_db:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(section_db)
    db.commit()
    return {'message': 'Бөлүм өчүрүлдү'}
