from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.client_auth import current_client
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.database.chat_models import ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest
from mysite.database.tour_review_models import TourReview
from mysite.database.tour_review_schema import TourReviewCreate, TourReviewOut

tour_reviews_router = APIRouter(prefix='/tours/{tour_id}/reviews', tags=['Tour Reviews'])


def require_active_tour(db: Session, tour_id: int) -> Tour:
    tour = db.query(Tour).filter(Tour.id == tour_id, Tour.is_active.is_(True)).first()
    if tour is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    return tour


@tour_reviews_router.get('/', response_model=list[TourReviewOut])
def list_tour_reviews(
    tour_id: int, db: Session = Depends(get_db), pagination: Pagination = Depends()
):
    require_active_tour(db, tour_id)
    return (
        db.query(TourReview)
        .filter(TourReview.tour_id == tour_id, TourReview.status == 'published')
        .order_by(TourReview.created_at.desc(), TourReview.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


def completed_trip(db: Session, client_id: int, tour_id: int) -> bool:
    """A finished request of the client with this tour among its services, from the site or chat."""
    return (
        db.query(TravelRequest.id)
        .filter(
            TravelRequest.client_id == client_id,
            TravelRequest.status == RequestStatusChoices.completed,
            cast(TravelRequest.selected_services, JSONB).contains(
                [{'kind': 'tour', 'id': tour_id}]
            ),
        )
        .first()
        is not None
    )


@tour_reviews_router.post('/', response_model=TourReviewOut, status_code=status.HTTP_201_CREATED)
def create_tour_review(
    tour_id: int,
    data: TourReviewCreate,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
):
    require_active_tour(db, tour_id)
    if not completed_trip(db, client.id, tour_id):
        raise HTTPException(status_code=403, detail=error_detail('review_requires_trip'))
    profile = db.query(ClientProfile).filter(ClientProfile.client_id == client.id).first()
    display_name = profile.name.strip() if profile and profile.name.strip() else client.username
    review = TourReview(
        tour_id=tour_id,
        client_id=client.id,
        display_name=display_name[:100],
        rating=data.rating,
        text=data.text,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=error_detail('conflict')) from exc
    db.refresh(review)
    return review


@tour_reviews_router.delete('/{review_id}/', status_code=status.HTTP_204_NO_CONTENT)
def delete_tour_review(
    tour_id: int,
    review_id: int,
    response: Response,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
):
    review = (
        db.query(TourReview)
        .filter(
            TourReview.id == review_id,
            TourReview.tour_id == tour_id,
            TourReview.client_id == client.id,
        )
        .first()
    )
    if review is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))
    db.delete(review)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
