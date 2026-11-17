from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import AboutSection
from mysite.database.schemas.content import AboutSectionOutSchema
from mysite.translations.content import Language, localized

about_section_router = APIRouter(prefix='/about-sections', tags=['About Sections'])


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
