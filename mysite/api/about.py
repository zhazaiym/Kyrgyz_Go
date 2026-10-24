
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.translations.content import Language, localized, update_translations
from mysite.database.models import About
from mysite.database.schema import (
    AboutInputSchema,
    AboutUpdateSchema,
    AboutOutSchema
)

about_router = APIRouter(prefix="/abouts", tags=["About"])


@about_router.post("/", response_model=AboutOutSchema, dependencies=[Depends(get_current_admin)])
def create_about(data: AboutInputSchema, db: Session = Depends(get_db)):
    about_db = About(**data.model_dump())
    db.add(about_db)
    update_translations(about_db)
    db.commit()
    db.refresh(about_db)
    return about_db


@about_router.get("/", response_model=list[AboutOutSchema])
def list_about(lang: Language = "ru", db: Session = Depends(get_db)):
    records = db.query(About).filter(About.is_active.is_(True)).all()
    return [localized(record, lang) for record in records]


@about_router.get("/{about_id}/", response_model=AboutOutSchema)
def detail_about(about_id: int, lang: Language = "ru", db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db or not about_db.is_active:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")
    return localized(about_db, lang)


@about_router.put("/{about_id}/", response_model=AboutOutSchema, dependencies=[Depends(get_current_admin)])
def update_about(about_id: int, data: AboutUpdateSchema, db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(about_db, key, value)

    update_translations(about_db)
    db.commit()
    db.refresh(about_db)
    return about_db


@about_router.delete("/{about_id}/", dependencies=[Depends(get_current_admin)])
def delete_about(about_id: int, db: Session = Depends(get_db)):
    about_db = db.get(About, about_id)
    if not about_db:
        raise HTTPException(status_code=404, detail="Маалымат табылган жок")

    db.delete(about_db)
    db.commit()
    return {"message": "Маалымат өчүрүлдү"}
