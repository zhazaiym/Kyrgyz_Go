from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Tour, TourProgram
from mysite.database.schemas.catalogue import TourProgramOutSchema
from mysite.translations.content import Language, localized

tour_program_router = APIRouter(prefix='/tour-programs', tags=['Tour Programs'])


@tour_program_router.get('/', response_model=list[TourProgramOutSchema])
def list_tour_programs(
    tour_id: int | None = None,
    lang: Language = 'ru',
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    query = db.query(TourProgram).join(Tour).filter(Tour.is_active.is_(True))
    if tour_id is not None:
        parent = db.get(Tour, tour_id)
        if parent is None or not parent.is_active:
            raise HTTPException(404, detail=error_detail('not_found'))
        query = query.filter(TourProgram.tour_id == tour_id)
    return [
        localized(record, lang)
        for record in query.order_by(TourProgram.day_number)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    ]


@tour_program_router.get('/{program_id}/', response_model=TourProgramOutSchema)
def detail_tour_program(program_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db or not program_db.tour.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    return localized(program_db, lang)
