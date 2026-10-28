from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.booking import require_chat_booking
from mysite.api.filter_utils import Pagination
from mysite.api.selection_status import require_status_transition
from mysite.database.chat_models import ChatBookingLink
from mysite.database.db import get_db
from mysite.database.models import TravelRequest
from mysite.database.schema import TravelRequestOutSchema, TravelRequestUpdateSchema
from mysite.database.travel_request_queries import list_travel_requests as query_travel_requests

travel_request_router = APIRouter(prefix='/travel-requests', tags=['Travel Requests'])


@travel_request_router.post('/', include_in_schema=False)
def create_travel_request():
    require_chat_booking()


@travel_request_router.get(
    '/', response_model=list[TravelRequestOutSchema], dependencies=[Depends(get_current_admin)]
)
def list_travel_requests(db: Session = Depends(get_db), pagination: Pagination = Depends()):
    return query_travel_requests(db, pagination.offset, pagination.limit)


@travel_request_router.get(
    '/{request_id}/',
    response_model=TravelRequestOutSchema,
    dependencies=[Depends(get_current_admin)],
)
def detail_travel_request(request_id: int, db: Session = Depends(get_db)):
    request_db = db.get(TravelRequest, request_id)

    if request_db is None:
        raise HTTPException(status_code=404, detail='Заявка табылган жок')

    return request_db


@travel_request_router.put(
    '/{request_id}/',
    response_model=TravelRequestOutSchema,
    dependencies=[Depends(get_current_admin)],
)
def update_travel_request(
    request_id: int, request: TravelRequestUpdateSchema, db: Session = Depends(get_db)
):
    request_db = db.get(TravelRequest, request_id, with_for_update=True, populate_existing=True)

    if request_db is None:
        raise HTTPException(status_code=404, detail='Заявка табылган жок')

    data = request.model_dump(exclude_unset=True)
    if 'status' in data:
        require_status_transition(request_db.status, data['status'])

    for key, value in data.items():
        setattr(request_db, key, value)

    db.commit()
    db.refresh(request_db)

    return request_db


@travel_request_router.delete('/{request_id}/', dependencies=[Depends(get_current_admin)])
def delete_travel_request(request_id: int, db: Session = Depends(get_db)):
    request_db = db.get(TravelRequest, request_id)

    if request_db is None:
        raise HTTPException(status_code=404, detail='Заявка табылган жок')

    if db.query(ChatBookingLink.id).filter(ChatBookingLink.request_id == request_id).first():
        raise HTTPException(
            409, 'Submitted chat requests must be retained; update their status instead'
        )
    db.delete(request_db)
    db.commit()

    return {'message': 'Заявка өчүрүлдү'}
