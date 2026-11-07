from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination
from mysite.api.selection_status import linked_request, processing_status, require_status_transition
from mysite.api.travel_selection import selection_context, selection_data
from mysite.database.chat_models import ChatClient
from mysite.database.db import get_db
from mysite.database.models import Admin
from mysite.database.selection_models import TravelSelection
from mysite.database.selection_statuses import SELECTION_TO_REQUEST_STATUS, SelectionStatus

manager_selection_router = APIRouter(
    prefix='/manager/travel-selections', tags=['Manager Travel Selections']
)


class SelectionStatusUpdate(BaseModel):
    status: SelectionStatus


@manager_selection_router.get('/')
def list_all_selections(
    current_admin: Admin = Depends(require_admin_roles('manager')),
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
    current_admin: Admin = Depends(require_admin_roles('manager')),
    db: Session = Depends(get_db),
):
    selection = db.get(TravelSelection, selection_id)

    if not selection:
        raise HTTPException(404, error_detail('not_found'))

    data = selection_data(db, selection)

    client = db.get(ChatClient, selection.client_id)

    data['client_code'] = f'KG-{selection.client_id:06d}'
    data['username'] = client.username if client else None

    return data


@manager_selection_router.patch('/{selection_id}/status/')
def update_selection_status(
    selection_id: int,
    data: SelectionStatusUpdate,
    current_admin: Admin = Depends(require_admin_roles('manager')),
    db: Session = Depends(get_db),
):
    selection = db.get(TravelSelection, selection_id, with_for_update=True, populate_existing=True)

    if selection is None:
        raise HTTPException(404, error_detail('not_found'))

    # Сначала получаем связанную заявку.
    travel_request = linked_request(db, selection, for_update=True)

    # Проверяем ограничения до изменения объектов.
    if data.status == SelectionStatus.draft and (
        selection.session_id is not None or travel_request is not None
    ):
        raise HTTPException(409, error_detail('conflict'))

    current_status = processing_status(selection, travel_request)
    require_status_transition(current_status, data.status.value)

    # Только после проверок изменяем статусы.
    selection.status = data.status.value

    if travel_request is not None:
        travel_request.status = SELECTION_TO_REQUEST_STATUS[data.status]

    db.commit()
    db.refresh(selection)

    return selection_data(db, selection)
