from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.db import get_db
from mysite.database.models import Tour, TourVideo
from mysite.database.schemas.catalogue import TourVideoOutSchema

tour_video_router = APIRouter(prefix='/tour-videos', tags=['Tour Videos'])


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
