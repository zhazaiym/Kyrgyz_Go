from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mysite.api.client_auth import current_client
from mysite.database.chat_models import ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db
from mysite.database.models import Tour
from mysite.database.tour_review_models import TourReview
from mysite.database.tour_review_schema import TourReviewCreate, TourReviewOut

tour_reviews_router = APIRouter(prefix='/tours/{tour_id}/reviews', tags=['Tour Reviews'])


def require_active_tour(db: Session, tour_id: int) -> Tour:
    tour = db.query(Tour).filter(Tour.id == tour_id, Tour.is_active.is_(True)).first()
    if tour is None:
        raise HTTPException(status_code=404, detail='Tour not found')
    return tour


@tour_reviews_router.get('/', response_model=list[TourReviewOut])
def list_tour_reviews(tour_id: int, db: Session = Depends(get_db)):
    require_active_tour(db, tour_id)
    return (
        db.query(TourReview)
        .filter(TourReview.tour_id == tour_id)
        .order_by(TourReview.created_at.desc(), TourReview.id.desc())
        .all()
    )


@tour_reviews_router.post('/', response_model=TourReviewOut, status_code=status.HTTP_201_CREATED)
def create_tour_review(
    tour_id: int,
    data: TourReviewCreate,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
):
    require_active_tour(db, tour_id)
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
        raise HTTPException(status_code=409, detail='You have already reviewed this tour') from exc
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
        raise HTTPException(status_code=404, detail='Review not found')
    db.delete(review)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
