from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.client_auth import current_client
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Trekking, TrekkingImage
from mysite.database.schemas.catalogue import (TrekkingImageInputSchema, TrekkingImageOutSchema,
                                               TrekkingImageUpdateSchema)

trekking_image_router = APIRouter(prefix='/trekking-images', tags=['Trekking Images'])


@trekking_image_router.post(
    '/',
    response_model=TrekkingImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_trekking_image(trekking_image: TrekkingImageInputSchema, db: Session = Depends(get_db)):
    trekking_db = db.get(Trekking, trekking_image.trekking_id)

    if trekking_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    image_db = TrekkingImage(**trekking_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@trekking_image_router.get(
    '/', response_model=list[TrekkingImageOutSchema], dependencies=[Depends(current_client)]
)
def list_trekking_images(
    trekking_id: int | None = None,
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    query = db.query(TrekkingImage).join(Trekking).filter(Trekking.is_active.is_(True))
    if trekking_id is not None:
        query = query.filter(TrekkingImage.trekking_id == trekking_id)
    return (
        query.order_by(TrekkingImage.order, TrekkingImage.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@trekking_image_router.get(
    '/{image_id}/', response_model=TrekkingImageOutSchema, dependencies=[Depends(current_client)]
)
def detail_trekking_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None or not image_db.trekking.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return image_db


@trekking_image_router.put(
    '/{image_id}/',
    response_model=TrekkingImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_trekking_image(
    image_id: int, trekking_image: TrekkingImageUpdateSchema, db: Session = Depends(get_db)
):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = trekking_image.model_dump(exclude_unset=True)

    if 'trekking_id' in data:
        if data['trekking_id'] is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        trekking_db = db.get(Trekking, data['trekking_id'])

        if trekking_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    for key, value in data.items():
        setattr(image_db, key, value)

    db.commit()
    db.refresh(image_db)

    return image_db


@trekking_image_router.delete(
    '/{image_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_trekking_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TrekkingImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(image_db)
    db.commit()

    return {'message': 'Треккингдин сүрөтү өчүрүлдү'}
