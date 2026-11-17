from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Trekking, TrekkingProgram
from mysite.database.schemas.catalogue import TrekkingProgramOutSchema
from mysite.translations.content import Language, localized

trekking_program_router = APIRouter(prefix='/trekking-programs', tags=['Trekking Programs'])


@trekking_program_router.get('/', response_model=list[TrekkingProgramOutSchema])
def list_trekking_programs(
    lang: Language = 'ru',
    trekking_id: int | None = None,
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    query = db.query(TrekkingProgram).join(Trekking).filter(Trekking.is_active.is_(True))

    if trekking_id is not None:
        parent = db.get(Trekking, trekking_id)
        if parent is None or not parent.is_active:
            raise HTTPException(404, detail=error_detail('not_found'))
        query = query.filter(TrekkingProgram.trekking_id == trekking_id)

    records = (
        query.order_by(TrekkingProgram.trekking_id, TrekkingProgram.day_number, TrekkingProgram.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return [localized(record, lang) for record in records]


@trekking_program_router.get('/{program_id}/', response_model=TrekkingProgramOutSchema)
def detail_trekking_program(program_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None or not program_db.trekking.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(program_db, lang)
