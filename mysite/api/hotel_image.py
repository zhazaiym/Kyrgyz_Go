
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.database.models import Hotel, HotelImage
from mysite.database.schema import (
    HotelImageInputSchema,
    HotelImageUpdateSchema,
    HotelImageOutSchema
)


hotel_image_router = APIRouter(
    prefix="/hotel-images",
    tags=["Hotel Images"]
)


@hotel_image_router.post("/", response_model=HotelImageOutSchema, dependencies=[Depends(get_current_admin)])
def create_hotel_image(
    hotel_image: HotelImageInputSchema,
    db: Session = Depends(get_db)
):
    hotel_db = db.get(Hotel, hotel_image.hotel_id)

    if hotel_db is None:
        raise HTTPException(
            status_code=404,
            detail="Мейманкана табылган жок"
        )

    hotel_image_db = HotelImage(
        **hotel_image.model_dump()
    )

    db.add(hotel_image_db)
    db.commit()
    db.refresh(hotel_image_db)

    return hotel_image_db


@hotel_image_router.get("/", response_model=list[HotelImageOutSchema])
def list_hotel_images(
    db: Session = Depends(get_db)
):
    return db.query(HotelImage).order_by(
        HotelImage.order,
        HotelImage.id
    ).all()


@hotel_image_router.get("/{image_id}/", response_model=HotelImageOutSchema)
def detail_hotel_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    return hotel_image_db


@hotel_image_router.put("/{image_id}/", response_model=HotelImageOutSchema, dependencies=[Depends(get_current_admin)])
def update_hotel_image(
    image_id: int,
    hotel_image: HotelImageUpdateSchema,
    db: Session = Depends(get_db)
):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    data = hotel_image.model_dump(exclude_unset=True)

    if "hotel_id" in data:
        if data["hotel_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Мейманкана милдеттүү"
            )

        hotel_db = db.get(Hotel, data["hotel_id"])

        if hotel_db is None:
            raise HTTPException(
                status_code=404,
                detail="Мейманкана табылган жок"
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
        setattr(hotel_image_db, key, value)

    db.commit()
    db.refresh(hotel_image_db)

    return hotel_image_db


@hotel_image_router.delete("/{image_id}/", dependencies=[Depends(get_current_admin)])
def delete_hotel_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    db.delete(hotel_image_db)
    db.commit()

    return {
        "message": "Мейманкананын сүрөтү өчүрүлдү"
    }
