
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.database.models import Tour, TourProgram
from mysite.database.schema import (
    TourProgramInputSchema,
    TourProgramUpdateSchema,
    TourProgramOutSchema
)

tour_program_router = APIRouter(prefix="/tour-programs", tags=["Tour Programs"])


@tour_program_router.post("/", response_model=TourProgramOutSchema)
def create_tour_program(data: TourProgramInputSchema, db: Session = Depends(get_db)):
    if not db.get(Tour, data.tour_id):
        raise HTTPException(status_code=404, detail="Тур табылган жок")

    program_db = TourProgram(**data.model_dump())
    db.add(program_db)
    db.commit()
    db.refresh(program_db)
    return program_db


@tour_program_router.get("/", response_model=list[TourProgramOutSchema])
def list_tour_programs(tour_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(TourProgram)
    if tour_id is not None:
        query = query.filter(TourProgram.tour_id == tour_id)
    return query.order_by(TourProgram.day_number).all()


@tour_program_router.get("/{program_id}/", response_model=TourProgramOutSchema)
def detail_tour_program(program_id: int, db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db:
        raise HTTPException(status_code=404, detail="Программа табылган жок")
    return program_db


@tour_program_router.put("/{program_id}/", response_model=TourProgramOutSchema)
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

    db.commit()
    db.refresh(program_db)
    return program_db


@tour_program_router.delete("/{program_id}/")
def delete_tour_program(program_id: int, db: Session = Depends(get_db)):
    program_db = db.get(TourProgram, program_id)
    if not program_db:
        raise HTTPException(status_code=404, detail="Программа табылган жок")

    db.delete(program_db)
    db.commit()
    return {"message": "Программа өчүрүлдү"}
