"""Photo galleries of tours, hotels, transport, helicopter tours and trekking: one set of routes."""

import inspect

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail, success_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import (HelicopterImage, HelicopterTour, Hotel, HotelImage, Tour,
                                    TourImage, Transport, TransportImage, Trekking, TrekkingImage)
from mysite.database.schemas import catalogue


def found(db: Session, model, identity):
    record = db.get(model, identity)
    if record is None:
        raise HTTPException(404, detail=error_detail('not_found'))
    return record


def image_router(*, key: str, parent, image, schema: str) -> APIRouter:
    """CRUD routes for the photos of one kind of catalogue record.

    ``key`` is the record kind: the photo links to it by ``f'{key}_id'`` and
    reaches it through the ``key`` relationship. ``schema`` is the common
    prefix of the input, update and output schemas in ``catalogue``.
    """
    parent_id = f'{key}_id'
    input_schema = getattr(catalogue, f'{schema}InputSchema')
    update_schema = getattr(catalogue, f'{schema}UpdateSchema')
    out_schema = getattr(catalogue, f'{schema}OutSchema')
    editor = [Depends(require_admin_roles('catalog_editor'))]
    router = APIRouter(prefix=f'/{key}-images', tags=[f'{key.capitalize()} Images'])

    def owner(**query):
        return query[parent_id]

    owner.__signature__ = inspect.Signature(
        [
            inspect.Parameter(
                parent_id, inspect.Parameter.KEYWORD_ONLY, default=None, annotation=int | None
            )
        ]
    )

    @router.post('/', response_model=out_schema, dependencies=editor, name=f'create_{key}_image')
    def create(data: input_schema, db: Session = Depends(get_db)):
        found(db, parent, getattr(data, parent_id))
        record = image(**data.model_dump())
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @router.get('/', response_model=list[out_schema], name=f'list_{key}_images')
    def listing(
        owner_id: int | None = Depends(owner),
        db: Session = Depends(get_db),
        pagination: Pagination = Depends(),
    ):
        query = db.query(image).join(parent).filter(parent.is_active.is_(True))
        if owner_id is not None:
            record = db.get(parent, owner_id)
            if record is None or not record.is_active:
                raise HTTPException(404, detail=error_detail('not_found'))
            query = query.filter(getattr(image, parent_id) == owner_id)
        return (
            query.order_by(image.order, image.id)
            .offset(pagination.offset)
            .limit(pagination.limit)
            .all()
        )

    @router.get('/{image_id}/', response_model=out_schema, name=f'detail_{key}_image')
    def detail(image_id: int, db: Session = Depends(get_db)):
        record = db.get(image, image_id)
        if record is None or not getattr(record, key).is_active:
            raise HTTPException(404, detail=error_detail('not_found'))
        return record

    @router.put(
        '/{image_id}/', response_model=out_schema, dependencies=editor, name=f'update_{key}_image'
    )
    def update(image_id: int, data: update_schema, db: Session = Depends(get_db)):
        record = found(db, image, image_id)
        values = data.model_dump(exclude_unset=True)
        if parent_id in values:
            if values[parent_id] is None:
                raise HTTPException(400, detail=error_detail('invalid_request'))
            found(db, parent, values[parent_id])
        for name, value in values.items():
            setattr(record, name, value)
        db.commit()
        db.refresh(record)
        return record

    @router.delete('/{image_id}/', dependencies=editor, name=f'delete_{key}_image')
    def delete(image_id: int, db: Session = Depends(get_db)):
        db.delete(found(db, image, image_id))
        db.commit()
        return success_detail('deleted')

    return router


tour_image_router = image_router(key='tour', parent=Tour, image=TourImage, schema='TourImage')
hotel_image_router = image_router(key='hotel', parent=Hotel, image=HotelImage, schema='HotelImage')
transport_image_router = image_router(
    key='transport', parent=Transport, image=TransportImage, schema='TransportImage'
)
helicopter_image_router = image_router(
    key='helicopter', parent=HelicopterTour, image=HelicopterImage, schema='HelicopterImage'
)
trekking_image_router = image_router(
    key='trekking', parent=Trekking, image=TrekkingImage, schema='TrekkingImage'
)
