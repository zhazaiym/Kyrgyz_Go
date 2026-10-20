
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Transport, TransportImage
from mysite.database.schema import (
    TransportImageInputSchema,
    TransportImageUpdateSchema,
    TransportImageOutSchema
)


transport_image_router = APIRouter(
    prefix="/transport-images",
    tags=["Transport Images"]
)


@transport_image_router.post("/", response_model=TransportImageOutSchema)
def create_transport_image(
    transport_image: TransportImageInputSchema,
    db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_image.transport_id)

    if transport_db is None:
        raise HTTPException(
            status_code=404,
            detail="Транспорт табылган жок"
        )

    image_db = TransportImage(**transport_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@transport_image_router.get("/", response_model=list[TransportImageOutSchema])
def list_transport_images(
    db: Session = Depends(get_db)
):
    return db.query(TransportImage).order_by(
        TransportImage.order,
        TransportImage.id
    ).all()


@transport_image_router.get("/{image_id}/", response_model=TransportImageOutSchema)
def detail_transport_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(TransportImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    return image_db


@transport_image_router.put("/{image_id}/", response_model=TransportImageOutSchema)
def update_transport_image(
    image_id: int,
    transport_image: TransportImageUpdateSchema,
    db: Session = Depends(get_db)
):
    image_db = db.get(TransportImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    data = transport_image.model_dump(exclude_unset=True)

    if "transport_id" in data:
        if data["transport_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Транспорт милдеттүү"
            )

        transport_db = db.get(Transport, data["transport_id"])

        if transport_db is None:
            raise HTTPException(
                status_code=404,
                detail="Транспорт табылган жок"
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


@transport_image_router.delete("/{image_id}/")
def delete_transport_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    image_db = db.get(TransportImage, image_id)

    if image_db is None:
        raise HTTPException(
            status_code=404,
            detail="Сүрөт табылган жок"
        )

    db.delete(image_db)
    db.commit()

    return {
        "message": "Транспорттун сүрөтү өчүрүлдү"
    }
