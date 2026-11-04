from sqlalchemy.orm import Session

from mysite.database.models import TravelRequest


def list_travel_requests(db: Session, offset: int, limit: int):
    return (
        db.query(TravelRequest).order_by(TravelRequest.id.desc()).offset(offset).limit(limit).all()
    )
