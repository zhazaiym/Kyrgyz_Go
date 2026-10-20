
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from mysite.database.db import get_db
from mysite.database.models import Tour, TourImage
from mysite.database.schema import (
    TourImageInputSchema,
    TourImageUpdateSchema,
    TourImageOutSchema
)

tour_image_router = APIRouter(prefix="/tour-images", tags=["Tour Images"])


@tour_image_router.post("/", response_model=TourImageOutSchema)
def create_tour_image(data: TourImageInputSchema, db: Session = Depends(get_db)):
    if not db.get(Tour, data.tour_id):
        raise HTTPException(status_code=404, detail="Тур табылган жок")

    image_db = TourImage(**data.model_dump())
    db.add(image_db)
    db.commit()
    db.refresh(image_db)
    return image_db


@tour_image_router.get("/", response_model=list[TourImageOutSchema])
def list_tour_images(tour_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(TourImage)
    if tour_id is not None:
        query = query.filter(TourImage.tour_id == tour_id)
    return query.order_by(TourImage.order).all()


@tour_image_router.get("/{image_id}/", response_model=TourImageOutSchema)
def detail_tour_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TourImage, image_id)
    if not image_db:
        raise HTTPException(status_code=404, detail="Сүрөт табылган жок")
    return image_db


@tour_image_router.put("/{image_id}/", response_model=TourImageOutSchema)
def update_tour_image(image_id: int, data: TourImageUpdateSchema, db: Session = Depends(get_db)):
    image_db = db.get(TourImage, image_id)
    if not image_db:
        raise HTTPException(status_code=404, detail="Сүрөт табылган жок")

    values = data.model_dump(exclude_unset=True)
    if "tour_id" in values:
        if values["tour_id"] is None or not db.get(Tour, values["tour_id"]):
            raise HTTPException(status_code=404, detail="Тур табылган жок")

    for key, value in values.items():
        setattr(image_db, key, value)

    db.commit()
    db.refresh(image_db)
    return image_db


@tour_image_router.delete("/{image_id}/")
def delete_tour_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TourImage, image_id)
    if not image_db:
        raise HTTPException(status_code=404, detail="Сүрөт табылган жок")

    db.delete(image_db)
    db.commit()
    return {"message": "Сүрөт өчүрүлдү"}
