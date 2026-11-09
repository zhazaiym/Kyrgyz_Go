from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Transport, TransportImage
from mysite.database.schemas.catalogue import (TransportImageInputSchema, TransportImageOutSchema,
                                               TransportImageUpdateSchema)

transport_image_router = APIRouter(prefix='/transport-images', tags=['Transport Images'])


@transport_image_router.post(
    '/',
    response_model=TransportImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_transport_image(
    transport_image: TransportImageInputSchema, db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_image.transport_id)

    if transport_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    image_db = TransportImage(**transport_image.model_dump())

    db.add(image_db)
    db.commit()
    db.refresh(image_db)

    return image_db


@transport_image_router.get('/', response_model=list[TransportImageOutSchema])
def list_transport_images(
    transport_id: int | None = None,
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    query = db.query(TransportImage).join(Transport).filter(Transport.is_active.is_(True))
    if transport_id is not None:
        parent = db.get(Transport, transport_id)
        if parent is None or not parent.is_active:
            raise HTTPException(404, detail=error_detail('not_found'))
        query = query.filter(TransportImage.transport_id == transport_id)
    return (
        query.order_by(TransportImage.order, TransportImage.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@transport_image_router.get('/{image_id}/', response_model=TransportImageOutSchema)
def detail_transport_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TransportImage, image_id)

    if image_db is None or not image_db.transport.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return image_db


@transport_image_router.put(
    '/{image_id}/',
    response_model=TransportImageOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_transport_image(
    image_id: int, transport_image: TransportImageUpdateSchema, db: Session = Depends(get_db)
):
    image_db = db.get(TransportImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = transport_image.model_dump(exclude_unset=True)

    if 'transport_id' in data:
        if data['transport_id'] is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        transport_db = db.get(Transport, data['transport_id'])

        if transport_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    for key, value in data.items():
        setattr(image_db, key, value)

    db.commit()
    db.refresh(image_db)

    return image_db


@transport_image_router.delete(
    '/{image_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_transport_image(image_id: int, db: Session = Depends(get_db)):
    image_db = db.get(TransportImage, image_id)

    if image_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(image_db)
    db.commit()

    return {'message': 'Транспорттун сүрөтү өчүрүлдү'}
