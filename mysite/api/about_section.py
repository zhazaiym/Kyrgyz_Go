
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.database.models import AboutSection
from mysite.database.schema import (
    AboutSectionInputSchema,
    AboutSectionUpdateSchema,
    AboutSectionOutSchema
)

about_section_router = APIRouter(
    prefix="/about-sections", tags=["About Sections"]
)


@about_section_router.post("/", response_model=AboutSectionOutSchema)
def create_about_section(data: AboutSectionInputSchema, db: Session = Depends(get_db)):
    section_db = AboutSection(**data.model_dump())
    db.add(section_db)
    db.commit()
    db.refresh(section_db)
    return section_db


@about_section_router.get("/", response_model=list[AboutSectionOutSchema])
def list_about_sections(db: Session = Depends(get_db)):
    return db.query(AboutSection).order_by(AboutSection.order).all()


@about_section_router.get("/{section_id}/", response_model=AboutSectionOutSchema)
def detail_about_section(section_id: int, db: Session = Depends(get_db)):
    section_db = db.get(AboutSection, section_id)
    if not section_db:
        raise HTTPException(status_code=404, detail="Бөлүм табылган жок")
    return section_db


@about_section_router.put("/{section_id}/", response_model=AboutSectionOutSchema)
def update_about_section(section_id: int, data: AboutSectionUpdateSchema, db: Session = Depends(get_db)):
    section_db = db.get(AboutSection, section_id)
    if not section_db:
        raise HTTPException(status_code=404, detail="Бөлүм табылган жок")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(section_db, key, value)

    db.commit()
    db.refresh(section_db)
    return section_db


@about_section_router.delete("/{section_id}/")
def delete_about_section(section_id: int, db: Session = Depends(get_db)):
    section_db = db.get(AboutSection, section_id)
    if not section_db:
        raise HTTPException(status_code=404, detail="Бөлүм табылган жок")

    db.delete(section_db)
    db.commit()
    return {"message": "Бөлүм өчүрүлдү"}
