from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.client_auth import current_client
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Trekking, TrekkingProgram
from mysite.database.schemas.catalogue import (TrekkingProgramInputSchema, TrekkingProgramOutSchema,
                                               TrekkingProgramUpdateSchema)
from mysite.translations.content import Language, localized, update_translations

trekking_program_router = APIRouter(prefix='/trekking-programs', tags=['Trekking Programs'])


@trekking_program_router.post(
    '/',
    response_model=TrekkingProgramOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_trekking_program(program: TrekkingProgramInputSchema, db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, program.trekking_id)

    if trekking_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    program_db = TrekkingProgram(**program.model_dump())

    db.add(program_db)
    update_translations(program_db)
    db.commit()
    db.refresh(program_db)

    return program_db


@trekking_program_router.get(
    '/', response_model=list[TrekkingProgramOutSchema], dependencies=[Depends(current_client)]
)
def list_trekking_programs(
    lang: Language = 'ru',
    trekking_id: int | None = None,
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    query = db.query(TrekkingProgram).join(Trekking).filter(Trekking.is_active.is_(True))

    if trekking_id is not None:
        query = query.filter(TrekkingProgram.trekking_id == trekking_id)

    records = (
        query.order_by(TrekkingProgram.trekking_id, TrekkingProgram.day_number, TrekkingProgram.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    return [localized(record, lang) for record in records]


@trekking_program_router.get(
    '/{program_id}/',
    response_model=TrekkingProgramOutSchema,
    dependencies=[Depends(current_client)],
)
def detail_trekking_program(program_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None or not program_db.trekking.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(program_db, lang)


@trekking_program_router.put(
    '/{program_id}/',
    response_model=TrekkingProgramOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_trekking_program(
    program_id: int, program: TrekkingProgramUpdateSchema, db: Session = Depends(get_db)
):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = program.model_dump(exclude_unset=True)

    if 'trekking_id' in data:
        if data['trekking_id'] is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        trekking_db = db.get(Trekking, data['trekking_id'])

        if trekking_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    if 'day_number' in data:
        if data['day_number'] is None or data['day_number'] < 1:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

    for key, value in data.items():
        setattr(program_db, key, value)

    update_translations(program_db)
    db.commit()
    db.refresh(program_db)

    return program_db


@trekking_program_router.delete(
    '/{program_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_trekking_program(program_id: int, db: Session = Depends(get_db)):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(program_db)
    db.commit()

    return {'message': 'Треккинг программасы өчүрүлдү'}
