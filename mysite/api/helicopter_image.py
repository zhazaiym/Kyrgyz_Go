
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import HelicopterTour, HelicopterImage
from mysite.database.schema import (
    HelicopterImageInputSchema,
    HelicopterImageUpdateSchema,
    HelicopterImageOutSchema
)


helicopter_image_router = APIRouter(
    prefix="/helicopter-images",
    tags=["Helicopter Images"]
)


@helicopter_image_router.post("/", response_model=HelicopterImageOutSchema)
def create_helicopter_image(
    helicopter_image: HelicopterImageInputSchema,
    db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_image.helicopter_id)

    if helicopter_db is None:
        raise HTTPException(
            status_code=404,
            detail="Вертолёт туру табылган жок"
        )

    image_db = HelicopterImage(**helicopter_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@helicopter_image_router.get("/", response_model=list[HelicopterImageOutSchema])
def list_helicopter_images(db: Session = Depends(get_db)):
    return db.query(HelicopterImage).order_by(
        HelicopterImage.order,
        HelicopterImage.id
    ).all()


@helicopter_image_router.get("/{image_id}/", response_model=HelicopterImageOutSchema)
def detail_helicopter_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    return image_db


@helicopter_image_router.put("/{image_id}/", response_model=HelicopterImageOutSchema)
def update_helicopter_image(
    image_id: int,
    helicopter_image: HelicopterImageUpdateSchema,
    db: Session = Depends(get_db)
):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    data = helicopter_image.model_dump(exclude_unset=True)

    if "helicopter_id" in data:
        if data["helicopter_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Вертолёт туру милдеттүү"
            )

        helicopter_db = db.get(HelicopterTour, data["helicopter_id"])

        if helicopter_db is None:
            raise HTTPException(
                status_code=404,
                detail="Вертолёт туру табылган жок"
            )

    if "image" in data and not data["image"]:
        raise HTTPException(
            status_code=400,
            detail="Сүрөттүн шилтемеси милдеттүү"
        )

    if "order" in data and data["order"] is None:
        raise HTTPException(
            status_code=400,
            detail="Сүрөттүн тартиби бош болбошу керек"
        )

    for key, value in data.items():
        setattr(image_db, key, value)

    db.commit()
    db.refresh(image_db)

    return image_db


@helicopter_image_router.delete("/{image_id}/")
def delete_helicopter_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    db.delete(image_db)
    db.commit()

    return {"message": "Вертолёттун сүрөтү өчүрүлдү"}
