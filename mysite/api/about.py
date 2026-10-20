
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.database.models import About
from mysite.database.schema import (
    AboutInputSchema,
    AboutUpdateSchema,
    AboutOutSchema
)

about_router = APIRouter(prefix="/abouts", tags=["About"])


@about_router.post("/", response_model=AboutOutSchema)
def create_about(data: AboutInputSchema, db: Session = Depends(get_db)):
    about_db = About(**data.model_dump())
    db.add(about_db)
    db.commit()
    db.refresh(about_db)
    return about_db


@about_router.get("/", response_model=list[AboutOutSchema])
def list_about(db: Session = Depends(get_db)):
    return db.query(About).all()


@about_router.get("/{about_id}/", response_model=AboutOutSchema)
def detail_about(about_id: int, db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")
    return about_db


@about_router.put("/{about_id}/", response_model=AboutOutSchema)
def update_about(about_id: int, data: AboutUpdateSchema, db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(about_db, key, value)

    db.commit()
    db.refresh(about_db)
    return about_db


@about_router.delete("/{about_id}/")
def delete_about(about_id: int, db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")

    db.delete(about_db)
    db.commit()
    return {"message": "Маалымат өчүрүлдү"}
