from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import HelicopterImage, HelicopterTour
from mysite.database.schema import (HelicopterImageInputSchema, HelicopterImageOutSchema,
                                    HelicopterImageUpdateSchema)

helicopter_image_router = APIRouter(prefix='/helicopter-images', tags=['Helicopter Images'])


@helicopter_image_router.post(
    '/', response_model=HelicopterImageOutSchema, dependencies=[Depends(get_current_admin)]
)
def create_helicopter_image(
    helicopter_image: HelicopterImageInputSchema, db: Session = Depends(get_db)
):
    helicopter_db = db.get(HelicopterTour, helicopter_image.helicopter_id)

    if helicopter_db is None:
        raise HTTPException(status_code=404, detail='Вертолёт туру табылган жок')

    image_db = HelicopterImage(**helicopter_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@helicopter_image_router.get(
    '/', response_model=list[HelicopterImageOutSchema], dependencies=[Depends(current_client)]
)
def list_helicopter_images(db: Session = Depends(get_db), pagination: Pagination = Depends()):
    return (
        db.query(HelicopterImage)
        .join(HelicopterTour)
        .filter(HelicopterTour.is_active.is_(True))
        .order_by(HelicopterImage.order, HelicopterImage.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@helicopter_image_router.get(
    '/{image_id}/', response_model=HelicopterImageOutSchema, dependencies=[Depends(current_client)]
)
def detail_helicopter_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None or not image_db.helicopter.is_active:
        raise HTTPException(status_code=404, detail='Сүрөт табылган жок')

    return image_db


@helicopter_image_router.put(
    '/{image_id}/',
    response_model=HelicopterImageOutSchema,
    dependencies=[Depends(get_current_admin)],
)
def update_helicopter_image(
    image_id: int, helicopter_image: HelicopterImageUpdateSchema, db: Session = Depends(get_db)
):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail='Сүрөт табылган жок')

    data = helicopter_image.model_dump(exclude_unset=True)

    if 'helicopter_id' in data:
        if data['helicopter_id'] is None:
            raise HTTPException(status_code=400, detail='Вертолёт туру милдеттүү')

        helicopter_db = db.get(HelicopterTour, data['helicopter_id'])

        if helicopter_db is None:
            raise HTTPException(status_code=404, detail='Вертолёт туру табылган жок')

    for key, value in data.items():
        setattr(image_db, key, value)

    db.commit()
    db.refresh(image_db)

    return image_db


@helicopter_image_router.delete('/{image_id}/', dependencies=[Depends(get_current_admin)])
def delete_helicopter_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(HelicopterImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail='Сүрөт табылган жок')

    db.delete(image_db)
    db.commit()

    return {'message': 'Вертолёттун сүрөтү өчүрүлдү'}
