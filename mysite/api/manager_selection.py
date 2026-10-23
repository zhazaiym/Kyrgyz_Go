
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Admin
from mysite.database.chat_models import ChatClient, ChatBookingLink
from mysite.database.selection_models import TravelSelection
from mysite.api.admin import get_current_admin
from mysite.api.travel_selection import selection_data


manager_selection_router = APIRouter(
    prefix="/manager/travel-selections",
    tags=["Manager Travel Selections"]
)


class SelectionStatusUpdate(BaseModel):
    status: str


@manager_selection_router.get("/")
def list_all_selections(
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    selections = (
        db.query(TravelSelection)
        .order_by(TravelSelection.created_at.desc())
        .all()
    )

    result = []

    for selection in selections:
        data = selection_data(db, selection)

        client = db.get(ChatClient, selection.client_id)

        data["client_code"] = f"KG-{selection.client_id:06d}"
        data["username"] = client.username if client else None

        booking = None

        if selection.session_id:
            booking = (
                db.query(ChatBookingLink)
                .filter(
                    ChatBookingLink.session_id == selection.session_id
                )
                .order_by(ChatBookingLink.id.desc())
                .first()
            )

        data["request_id"] = (
            booking.request_id if booking else None
        )

        result.append(data)

    return result


@manager_selection_router.get("/{selection_id}/")
def detail_manager_selection(
    selection_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    selection = db.get(TravelSelection, selection_id)

    if not selection:
        raise HTTPException(404, "Поездка не найдена")

    data = selection_data(db, selection)

    client = db.get(ChatClient, selection.client_id)

    data["client_code"] = f"KG-{selection.client_id:06d}"
    data["username"] = client.username if client else None

    return data


@manager_selection_router.patch("/{selection_id}/status/")
def update_selection_status(
    selection_id: int,
    data: SelectionStatusUpdate,
    current_admin: Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    selection = db.get(TravelSelection, selection_id)

    if not selection:
        raise HTTPException(404, "Поездка не найдена")

    allowed_statuses = {
        "draft",
        "in_progress",
        "completed",
        "cancelled"
    }

    if data.status not in allowed_statuses:
        raise HTTPException(
            422,
            "Недопустимый статус"
        )

    if selection.status == "completed":
        raise HTTPException(
            409,
            "Завершённую поездку нельзя изменить"
        )

    if data.status == "draft" and selection.session_id:
        raise HTTPException(
            409,
            "Нельзя вернуть поездку с чатом в черновик"
        )

    selection.status = data.status

    db.commit()
    db.refresh(selection)

    return selection_data(db, selection)
