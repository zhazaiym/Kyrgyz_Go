
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.api.booking import require_chat_booking
from mysite.database.models import TravelRequest
from mysite.database.schema import (
    TravelRequestUpdateSchema,
    TravelRequestOutSchema
)


travel_request_router = APIRouter(
    prefix="/travel-requests",
    tags=["Travel Requests"]
)


@travel_request_router.post("/", include_in_schema=False)
def create_travel_request():
    require_chat_booking()


@travel_request_router.get("/", response_model=list[TravelRequestOutSchema], dependencies=[Depends(get_current_admin)])
def list_travel_requests(db: Session = Depends(get_db)):
    return db.query(TravelRequest).order_by(
        TravelRequest.id.desc()
    ).all()


@travel_request_router.get("/{request_id}/", response_model=TravelRequestOutSchema, dependencies=[Depends(get_current_admin)])
def detail_travel_request(
    request_id: int,
    db: Session = Depends(get_db)
):
    request_db = db.get(TravelRequest, request_id)

    if request_db is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка табылган жок"
        )

    return request_db


@travel_request_router.put("/{request_id}/", response_model=TravelRequestOutSchema, dependencies=[Depends(get_current_admin)])
def update_travel_request(
    request_id: int,
    request: TravelRequestUpdateSchema,
    db: Session = Depends(get_db)
):
    request_db = db.get(TravelRequest, request_id)

    if request_db is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка табылган жок"
        )

    data = request.model_dump(exclude_unset=True)

    for field in ("name", "phone", "status"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=400,
                detail=f"{field} бош болбошу керек"
            )

    for key, value in data.items():
        setattr(request_db, key, value)

    db.commit()
    db.refresh(request_db)

    return request_db


@travel_request_router.delete("/{request_id}/", dependencies=[Depends(get_current_admin)])
def delete_travel_request(
    request_id: int,
    db: Session = Depends(get_db)
):
    request_db = db.get(TravelRequest, request_id)

    if request_db is None:
        raise HTTPException(
            status_code=404,
            detail="Заявка табылган жок"
        )

    db.delete(request_db)
    db.commit()

    return {"message": "Заявка өчүрүлдү"}
