
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.translations.content import Language, localized, update_translations
from mysite.database.models import Tour, TourProgram
from mysite.database.schema import (
    TourProgramInputSchema,
    TourProgramUpdateSchema,
    TourProgramOutSchema
)

tour_program_router = APIRouter(prefix="/tour-programs", tags=["Tour Programs"])


@tour_program_router.post("/", response_model=TourProgramOutSchema, dependencies=[Depends(get_current_admin)])
def create_tour_program(data: TourProgramInputSchema, db: Session = Depends(get_db)):
    if not db.get(Tour, data.tour_id):
        raise HTTPException(status_code=404, detail="Тур табылган жок")

    program_db = TourProgram(**data.model_dump())
    db.add(program_db)
    update_translations(program_db)
    db.commit()
    db.refresh(program_db)
    return program_db


@tour_program_router.get("/", response_model=list[TourProgramOutSchema], dependencies=[Depends(current_client)])
def list_tour_programs(tour_id: int | None = None, lang: Language = "ru", db: Session = Depends(get_db)):
    query = db.query(TourProgram).join(Tour).filter(Tour.is_active.is_(True))
    if tour_id is not None:
        query = query.filter(TourProgram.tour_id == tour_id)
    return [localized(record, lang) for record in query.order_by(TourProgram.day_number).all()]


@tour_program_router.get("/{program_id}/", response_model=TourProgramOutSchema, dependencies=[Depends(current_client)])
def detail_tour_program(program_id: int, lang: Language = "ru", db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db or not program_db.tour.is_active:
        raise HTTPException(status_code=404, detail="Программа табылган жок")
    return localized(program_db, lang)


@tour_program_router.put("/{program_id}/", response_model=TourProgramOutSchema, dependencies=[Depends(get_current_admin)])
def update_tour_program(program_id: int, data: TourProgramUpdateSchema, db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db:
        raise HTTPException(status_code=404, detail="Программа табылган жок")

    values = data.model_dump(exclude_unset=True)
    if "tour_id" in values:
        if values["tour_id"] is None or not db.get(Tour, values["tour_id"]):
            raise HTTPException(status_code=404, detail="Тур табылган жок")

    for key, value in values.items():
        setattr(program_db, key, value)

    update_translations(program_db)
    db.commit()
    db.refresh(program_db)
    return program_db


@tour_program_router.delete("/{program_id}/", dependencies=[Depends(get_current_admin)])
def delete_tour_program(program_id: int, db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db:
        raise HTTPException(status_code=404, detail="Программа табылган жок")

    db.delete(program_db)
    db.commit()
    return {"message": "Программа өчүрүлдү"}
