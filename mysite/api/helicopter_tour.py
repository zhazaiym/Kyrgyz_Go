
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.translations.content import Language, localized, update_translations
from mysite.database.models import HelicopterTour
from mysite.database.schema import (
    HelicopterTourInputSchema,
    HelicopterTourUpdateSchema,
    HelicopterTourOutSchema
)


helicopter_tour_router = APIRouter(
    prefix="/helicopter-tours",
    tags=["Helicopter Tours"]
)


@helicopter_tour_router.post("/", response_model=HelicopterTourOutSchema, dependencies=[Depends(get_current_admin)])
def create_helicopter_tour(
    helicopter: HelicopterTourInputSchema,
    db: Session = Depends(get_db)
):
    helicopter_db = HelicopterTour(**helicopter.model_dump())

    db.add(helicopter_db)
    update_translations(helicopter_db)
    db.commit()
    db.refresh(helicopter_db)

    return helicopter_db


@helicopter_tour_router.get("/", response_model=list[HelicopterTourOutSchema])
def list_helicopter_tours(
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    return [localized(record, lang) for record in db.query(HelicopterTour).all()]


@helicopter_tour_router.get("/{helicopter_id}/", response_model=HelicopterTourOutSchema)
def detail_helicopter_tour(
    helicopter_id: int,
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_id)

    if helicopter_db is None:
        raise HTTPException(
            status_code=404,
            detail="Вертолёт туру табылган жок"
        )

    return localized(helicopter_db, lang)


@helicopter_tour_router.put("/{helicopter_id}/", response_model=HelicopterTourOutSchema, dependencies=[Depends(get_current_admin)])
def update_helicopter_tour(
    helicopter_id: int,
    helicopter: HelicopterTourUpdateSchema,
    db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_id)

    if helicopter_db is None:
        raise HTTPException(
            status_code=404,
            detail="Вертолёт туру табылган жок"
        )

    data = helicopter.model_dump(exclude_unset=True)

    for field in ("title", "price", "price_unit", "is_active"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=400,
                detail=f"{field} бош болбошу керек"
            )

    for key, value in data.items():
        setattr(helicopter_db, key, value)

    update_translations(helicopter_db)
    db.commit()
    db.refresh(helicopter_db)

    return helicopter_db


@helicopter_tour_router.delete("/{helicopter_id}/", dependencies=[Depends(get_current_admin)])
def delete_helicopter_tour(
    helicopter_id: int,
    db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_id)

    if helicopter_db is None:
        raise HTTPException(
            status_code=404,
            detail="Вертолёт туру табылган жок"
        )

    db.delete(helicopter_db)
    db.commit()

    return {
        "message": "Вертолёт туру өчүрүлдү"
    }
