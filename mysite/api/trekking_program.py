from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Trekking, TrekkingProgram
from mysite.database.schema import (TrekkingProgramInputSchema, TrekkingProgramOutSchema,
                                    TrekkingProgramUpdateSchema)
from mysite.translations.content import Language, localized, update_translations

trekking_program_router = APIRouter(prefix='/trekking-programs', tags=['Trekking Programs'])


@trekking_program_router.post(
    '/', response_model=TrekkingProgramOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_trekking_program(program: TrekkingProgramInputSchema, db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, program.trekking_id)

    if trekking_db is None:
        raise HTTPException(status_code=404, detail='Треккинг табылган жок')

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
    lang: Language = 'ru', db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    return [
        localized(record, lang)
        for record in db.query(TrekkingProgram)
        .join(Trekking)
        .filter(Trekking.is_active.is_(True))
        .order_by(TrekkingProgram.trekking_id, TrekkingProgram.day_number)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    ]


@trekking_program_router.get(
    '/{program_id}/',
    response_model=TrekkingProgramOutSchema,
    dependencies=[Depends(current_client)],
)
def detail_trekking_program(program_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None or not program_db.trekking.is_active:
        raise HTTPException(status_code=404, detail='Треккинг программасы табылган жок')

    return localized(program_db, lang)


@trekking_program_router.put(
    '/{program_id}/',
    response_model=TrekkingProgramOutSchema,
    dependencies=[Depends(get_current_admin)],
)
def update_trekking_program(
    program_id: int, program: TrekkingProgramUpdateSchema, db: Session = Depends(get_db)
):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None:
        raise HTTPException(status_code=404, detail='Треккинг программасы табылган жок')

    data = program.model_dump(exclude_unset=True)

    if 'trekking_id' in data:
        if data['trekking_id'] is None:
            raise HTTPException(status_code=400, detail='Треккинг милдеттүү')

        trekking_db = db.get(Trekking, data['trekking_id'])

        if trekking_db is None:
            raise HTTPException(status_code=404, detail='Треккинг табылган жок')

    if 'day_number' in data:
        if data['day_number'] is None or data['day_number'] < 1:
            raise HTTPException(status_code=400, detail='Күндүн номери 1ден кем болбошу керек')

    for key, value in data.items():
        setattr(program_db, key, value)

    update_translations(program_db)
    db.commit()
    db.refresh(program_db)

    return program_db


@trekking_program_router.delete('/{program_id}/', dependencies=[Depends(get_current_admin)])
def delete_trekking_program(program_id: int, db: Session = Depends(get_db)):
    program_db = db.get(TrekkingProgram, program_id)

    if program_db is None:
        raise HTTPException(status_code=404, detail='Треккинг программасы табылган жок')

    db.delete(program_db)
    db.commit()

    return {'message': 'Треккинг программасы өчүрүлдү'}
