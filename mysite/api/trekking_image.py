
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.database.models import Trekking, TrekkingImage
from mysite.database.schema import (
    TrekkingImageInputSchema,
    TrekkingImageUpdateSchema,
    TrekkingImageOutSchema
)


trekking_image_router = APIRouter(
    prefix="/trekking-images",
    tags=["Trekking Images"]
)


@trekking_image_router.post("/", response_model=TrekkingImageOutSchema, dependencies=[Depends(get_current_admin)])
def create_trekking_image(
    trekking_image: TrekkingImageInputSchema,
    db: Session = Depends(get_db)
):
    trekking_db = db.get(Trekking, trekking_image.trekking_id)

    if trekking_db is None:
        raise HTTPException(
            status_code=404,
            detail="Треккинг табылган жок"
        )

    image_db = TrekkingImage(**trekking_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@trekking_image_router.get("/", response_model=list[TrekkingImageOutSchema], dependencies=[Depends(current_client)])
def list_trekking_images(db: Session = Depends(get_db)):
    return db.query(TrekkingImage).join(Trekking).filter(Trekking.is_active.is_(True)).order_by(
        TrekkingImage.order,
        TrekkingImage.id
    ).all()


@trekking_image_router.get("/{image_id}/", response_model=TrekkingImageOutSchema, dependencies=[Depends(current_client)])
def detail_trekking_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None or not image_db.trekking.is_active:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    return image_db


@trekking_image_router.put("/{image_id}/", response_model=TrekkingImageOutSchema, dependencies=[Depends(get_current_admin)])
def update_trekking_image(
    image_id: int,
    trekking_image: TrekkingImageUpdateSchema,
    db: Session = Depends(get_db)
):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    data = trekking_image.model_dump(exclude_unset=True)

    if "trekking_id" in data:
        if data["trekking_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Треккинг милдеттүү"
            )

        trekking_db = db.get(Trekking, data["trekking_id"])

        if trekking_db is None:
            raise HTTPException(
                status_code=404,
                detail="Треккинг табылган жок"
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


@trekking_image_router.delete("/{image_id}/", dependencies=[Depends(get_current_admin)])
def delete_trekking_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    db.delete(image_db)
    db.commit()

    return {"message": "Треккингдин сүрөтү өчүрүлдү"}
