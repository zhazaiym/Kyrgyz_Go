from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mysite.api.admin import get_current_admin
from mysite.api.filter_utils import Pagination
from mysite.api.selection_status import linked_request, processing_status
from mysite.api.travel_selection import selection_context, selection_data
from mysite.database.chat_models import ChatClient
from mysite.database.db import get_db
from mysite.database.models import Admin, RequestStatusChoices
from mysite.database.selection_models import TravelSelection

manager_selection_router = APIRouter(
    prefix='/manager/travel-selections', tags=['Manager Travel Selections']
)


class SelectionStatusUpdate(BaseModel):
    status: str


@manager_selection_router.get('/')
def list_all_selections(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    selections = (
        db.query(TravelSelection)
        .order_by(TravelSelection.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )

    result = []
    context = selection_context(db, selections, include_clients=True)

    for selection in selections:
        data = selection_data(db, selection, context)

        client = context.clients.get(selection.client_id)

        data['client_code'] = f'KG-{selection.client_id:06d}'
        data['username'] = client.username if client else None

        result.append(data)

    return result


@manager_selection_router.get('/{selection_id}/')
def detail_manager_selection(
    selection_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    selection = db.get(TravelSelection, selection_id)

    if not selection:
        raise HTTPException(404, 'Поездка не найдена')

    data = selection_data(db, selection)

    client = db.get(ChatClient, selection.client_id)

    data['client_code'] = f'KG-{selection.client_id:06d}'
    data['username'] = client.username if client else None

    return data


@manager_selection_router.patch('/{selection_id}/status/')
def update_selection_status(
    selection_id: int,
    data: SelectionStatusUpdate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    selection = db.get(TravelSelection, selection_id, with_for_update=True, populate_existing=True)

    if not selection:
        raise HTTPException(404, 'Поездка не найдена')

    allowed_statuses = {'draft', 'in_progress', 'completed', 'cancelled'}

    if data.status not in allowed_statuses:
        raise HTTPException(422, 'Недопустимый статус')

    request = linked_request(db, selection, for_update=True)
    current_status = processing_status(selection, request)
    if current_status == 'completed' and data.status != current_status:
        raise HTTPException(409, 'Завершённую поездку нельзя изменить')

    if data.status == 'draft' and selection.session_id:
        raise HTTPException(409, 'Нельзя вернуть поездку с чатом в черновик')

    selection.status = data.status
    if request is not None:
        request.status = RequestStatusChoices(data.status)

    db.commit()
    db.refresh(selection)

    return selection_data(db, selection)
