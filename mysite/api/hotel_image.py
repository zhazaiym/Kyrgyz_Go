from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.client_auth import current_client
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Hotel, HotelImage
from mysite.database.schemas.catalogue import (HotelImageInputSchema, HotelImageOutSchema,
                                               HotelImageUpdateSchema)

hotel_image_router = APIRouter(prefix='/hotel-images', tags=['Hotel Images'])


@hotel_image_router.post(
    '/',
    response_model=HotelImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_hotel_image(hotel_image: HotelImageInputSchema, db: Session = Depends(get_db)):
    hotel_db = db.get(Hotel, hotel_image.hotel_id)

    if hotel_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    hotel_image_db = HotelImage(**hotel_image.model_dump())

    db.add(hotel_image_db)
    db.commit()
    db.refresh(hotel_image_db)

    return hotel_image_db


@hotel_image_router.get(
    '/', response_model=list[HotelImageOutSchema], dependencies=[Depends(current_client)]
)
def list_hotel_images(
    hotel_id: int | None = None, db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    query = db.query(HotelImage).join(Hotel).filter(Hotel.is_active.is_(True))
    if hotel_id is not None:
        query = query.filter(HotelImage.hotel_id == hotel_id)
    return (
        query.order_by(HotelImage.order, HotelImage.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@hotel_image_router.get(
    '/{image_id}/', response_model=HotelImageOutSchema, dependencies=[Depends(current_client)]
)
def detail_hotel_image(image_id: int, db: Session = Depends(get_db)):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None or not hotel_image_db.hotel.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return hotel_image_db


@hotel_image_router.put(
    '/{image_id}/',
    response_model=HotelImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_hotel_image(
    image_id: int, hotel_image: HotelImageUpdateSchema, db: Session = Depends(get_db)
):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = hotel_image.model_dump(exclude_unset=True)

    if 'hotel_id' in data:
        if data['hotel_id'] is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        hotel_db = db.get(Hotel, data['hotel_id'])

        if hotel_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    for key, value in data.items():
        setattr(hotel_image_db, key, value)

    db.commit()
    db.refresh(hotel_image_db)

    return hotel_image_db


@hotel_image_router.delete(
    '/{image_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_hotel_image(image_id: int, db: Session = Depends(get_db)):
    hotel_image_db = db.get(HotelImage, image_id)

    if hotel_image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(hotel_image_db)
    db.commit()

    return {'message': 'Мейманкананын сүрөтү өчүрүлдү'}
