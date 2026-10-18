
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Tour, TourCategory
from mysite.database.schema import (
    TourInputSchema,
    TourUpdateSchema,
    TourOutSchema,
    TourDetailSchema
)


tour_router = APIRouter(
    prefix="/tours",
    tags=["Tours"]
)


@tour_router.post("/", response_model=TourOutSchema)
def create_tour(
    tour: TourInputSchema,
    db: Session = Depends(get_db)
):
    if tour.category_id is not None:
        category_db = db.get(TourCategory, tour.category_id)

        if category_db is None:
            raise HTTPException(
                status_code=404,
                detail="Категория табылган жок"
            )

    tour_db = Tour(**tour.model_dump())

    db.add(tour_db)
    db.commit()
    db.refresh(tour_db)

    return tour_db


@tour_router.get("/", response_model=list[TourOutSchema])
def list_tours(db: Session = Depends(get_db)):
    return db.query(Tour).filter(Tour.is_active.is_(True)).all()


@tour_router.get("/{tour_id}/", response_model=TourDetailSchema)
def detail_tour(
    tour_id: int,
    db: Session = Depends(get_db)
):
    tour_db = db.get(Tour, tour_id)

    if tour_db is None or not tour_db.is_active:
        raise HTTPException(
            status_code=404,
            detail="Тур табылган жок"
        )

    return tour_db


@tour_router.put("/{tour_id}/", response_model=TourOutSchema)
def update_tour(
    tour_id: int,
    tour: TourUpdateSchema,
    db: Session = Depends(get_db)
):
    tour_db = db.get(Tour, tour_id)

    if tour_db is None:
        raise HTTPException(
            status_code=404,
            detail="Тур табылган жок"
        )

    data = tour.model_dump(exclude_unset=True)

    if data.get("category_id") is not None:
        category_db = db.get(TourCategory, data["category_id"])

        if category_db is None:
            raise HTTPException(
                status_code=404,
                detail="Категория табылган жок"
            )

    for key, value in data.items():
        setattr(tour_db, key, value)

    db.commit()
    db.refresh(tour_db)

    return tour_db


@tour_router.delete("/{tour_id}/")
def delete_tour(
    tour_id: int,
    db: Session = Depends(get_db)
):
    tour_db = db.get(Tour, tour_id)

    if tour_db is None:
        raise HTTPException(
            status_code=404,
            detail="Тур табылган жок"
        )

    db.delete(tour_db)
    db.commit()

    return {"message": "Тур өчүрүлдү"}
