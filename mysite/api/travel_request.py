import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from mysite.admin.realtime import publish_new_request
from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.filter_utils import Pagination
from mysite.api.selected_services import selected_services
from mysite.api.selection_status import require_status_transition
from mysite.database.chat_models import ChatBookingLink, ChatClient
from mysite.database.client_profile import ClientProfile
from mysite.database.db import get_db
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest
from mysite.database.schemas.requests import TravelRequestOutSchema, TravelRequestUpdateSchema
from mysite.database.selection_models import TravelSelection
from mysite.database.travel_request_queries import list_travel_requests as query_travel_requests

travel_request_router = APIRouter(prefix='/travel-requests', tags=['Travel Requests'])


class TravelRequestCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    selection_id: int = Field(gt=0)
    travel_date: date
    travelers_count: int = Field(gt=0)
    phone: str = Field(min_length=7, max_length=25)
    message: str | None = Field(default=None, max_length=2000)

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        normalized = re.sub(r'[\s()\-]', '', value.strip())
        if not re.fullmatch(r'\+?[0-9]{7,15}', normalized):
            raise ValueError('Enter a valid phone number')
        return normalized

    @field_validator('message')
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


@travel_request_router.post('/', response_model=TravelRequestOutSchema, status_code=201)
def create_travel_request(
    data: TravelRequestCreate,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
):
    if data.travel_date < date.today():
        raise HTTPException(422, detail='Travel date cannot be in the past')

    selection = (
        db.query(TravelSelection)
        .filter(TravelSelection.id == data.selection_id, TravelSelection.client_id == client.id)
        .with_for_update()
        .first()
    )
    if selection is None:
        raise HTTPException(404, detail='Selection not found')
    if selection.status != 'draft' or selection.session_id:
        raise HTTPException(409, detail='Selection is no longer available for a direct request')

    state = {
        'tour_id': selection.tour_id,
        'hotel_id': selection.hotel_id,
        'transport_id': selection.transport_id,
    }
    services, missing = selected_services(db, state)
    if missing or not services:
        raise HTTPException(409, detail='Selection has no active services')

    profile = db.query(ClientProfile).filter(ClientProfile.client_id == client.id).first()
    tour = db.get(Tour, selection.tour_id) if selection.tour_id is not None else None
    request = TravelRequest(
        client_id=client.id,
        selection_id=selection.id,
        name=(profile.name.strip() if profile and profile.name.strip() else client.username),
        phone=data.phone,
        email=client.email,
        travel_date=data.travel_date,
        duration_days=tour.duration_days if tour else None,
        travelers_count=data.travelers_count,
        destination=tour.title if tour else None,
        message=data.message,
        selected_services=services,
        status=RequestStatusChoices.new,
    )
    selection.status = 'in_progress'
    db.add(request)
    db.commit()
    db.refresh(request)
    publish_new_request(request.id)
    return request


@travel_request_router.get('/me/', response_model=list[TravelRequestOutSchema])
def list_my_travel_requests(
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    return (
        db.query(TravelRequest)
        .filter(TravelRequest.client_id == client.id)
        .order_by(TravelRequest.created_at.desc(), TravelRequest.id.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )


@travel_request_router.delete('/me/{request_id}/', response_model=TravelRequestOutSchema)
def cancel_my_travel_request(
    request_id: int, client: ChatClient = Depends(current_client), db: Session = Depends(get_db)
):
    request = (
        db.query(TravelRequest)
        .filter(TravelRequest.id == request_id, TravelRequest.client_id == client.id)
        .with_for_update()
        .first()
    )
    if request is None:
        raise HTTPException(404, detail='Travel request not found')
    require_status_transition(request.status, RequestStatusChoices.cancelled)
    request.status = RequestStatusChoices.cancelled
    db.commit()
    db.refresh(request)
    return request


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

    for field in ('name', 'phone', 'status'):
        if field in data and data[field] is None:
            raise HTTPException(status_code=400, detail=f'{field} бош болбошу керек')

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

    if (
        request_db.selection_id is not None
        or db.query(ChatBookingLink.id).filter(ChatBookingLink.request_id == request_id).first()
    ):
        raise HTTPException(
            409, 'Submitted chat requests must be retained; update their status instead'
        )
    db.delete(request_db)
    db.commit()

    return {'message': 'Заявка өчүрүлдү'}
