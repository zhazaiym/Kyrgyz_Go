from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Tour, TourVideo
from mysite.database.schemas.catalogue import (TourVideoInputSchema, TourVideoOutSchema,
                                               TourVideoUpdateSchema)

tour_video_router = APIRouter(prefix='/tour-videos', tags=['Tour Videos'])


@tour_video_router.post(
    '/',
    response_model=TourVideoOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_tour_video(data: TourVideoInputSchema, db: Session = Depends(get_db)):
    if not db.get(Tour, data.tour_id):
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    video_db = TourVideo(**data.model_dump())
    db.add(video_db)
    db.commit()
    db.refresh(video_db)
    return video_db


@tour_video_router.get('/', response_model=list[TourVideoOutSchema])
def list_tour_videos(
    tour_id: int | None = None, db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    query = db.query(TourVideo).join(Tour).filter(Tour.is_active.is_(True))
    if tour_id is not None:
        parent = db.get(Tour, tour_id)
        if parent is None or not parent.is_active:
            raise HTTPException(404, detail=error_detail('not_found'))
        query = query.filter(TourVideo.tour_id == tour_id)
    return (
        query.order_by(TourVideo.order, TourVideo.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@tour_video_router.get('/{video_id}/', response_model=TourVideoOutSchema)
def detail_tour_video(video_id: int, db: Session = Depends(get_db)):
    video_db = db.get(TourVideo, video_id)
    if not video_db or not video_db.tour.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    return video_db


@tour_video_router.put(
    '/{video_id}/',
    response_model=TourVideoOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_tour_video(video_id: int, data: TourVideoUpdateSchema, db: Session = Depends(get_db)):
    video_db = db.get(TourVideo, video_id)
    if not video_db:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    values = data.model_dump(exclude_unset=True)
    if 'tour_id' in values:
        if values['tour_id'] is None or not db.get(Tour, values['tour_id']):
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    for key, value in values.items():
        setattr(video_db, key, value)

    db.commit()
    db.refresh(video_db)
    return video_db


@tour_video_router.delete(
    '/{video_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_tour_video(video_id: int, db: Session = Depends(get_db)):
    video_db = db.get(TourVideo, video_id)
    if not video_db:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    db.delete(video_db)
    db.commit()
    return {'message': 'Видео удалено'}
