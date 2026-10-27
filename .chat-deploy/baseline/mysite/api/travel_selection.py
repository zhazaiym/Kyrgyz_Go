
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Tour, Hotel, Transport
from mysite.database.selection_models import TravelSelection
from mysite.database.chat_models import (
    ChatClient,
    ChatSession,
    ChatMessage,
)
from mysite.api.client_auth import current_client


selection_router = APIRouter(
    prefix="/travel-selections",
    tags=["Travel Selections"]
)


# SCHEMAS

class SelectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tour_id: int | None = Field(default=None, gt=0)
    hotel_id: int | None = Field(default=None, gt=0)
    transport_id: int | None = Field(default=None, gt=0)


class SelectionUpdate(SelectionInput):
    pass


# HELPERS

def validate_items(db, tour_id, hotel_id, transport_id):
    if all(
        value is None
        for value in (tour_id, hotel_id, transport_id)
    ):
        raise HTTPException(
            status_code=422,
            detail="Выберите хотя бы одну услугу"
        )

    for model, item_id, name in [
        (Tour, tour_id, "Тур"),
        (Hotel, hotel_id, "Отель"),
        (Transport, transport_id, "Транспорт"),
    ]:
        if item_id is not None:
            item = db.get(model, item_id)

            if not item or not item.is_active:
                raise HTTPException(
                    status_code=404,
                    detail=f"{name} не найден или недоступен"
                )


def get_selection(db, selection_id, client_id):
    selection = db.get(TravelSelection, selection_id)

    if not selection or selection.client_id != client_id:
        raise HTTPException(
            status_code=404,
            detail="Поездка не найдена"
        )

    return selection


def selection_data(db, selection):
    tour = (
        db.get(Tour, selection.tour_id)
        if selection.tour_id is not None else None
    )

    hotel = (
        db.get(Hotel, selection.hotel_id)
        if selection.hotel_id is not None else None
    )

    transport = (
        db.get(Transport, selection.transport_id)
        if selection.transport_id is not None else None
    )

    return {
        "id": selection.id,
        "client_id": selection.client_id,
        "tour_id": selection.tour_id,
        "tour_name": tour.title if tour else None,
        "hotel_id": selection.hotel_id,
        "hotel_name": hotel.name if hotel else None,
        "transport_id": selection.transport_id,
        "transport_name": transport.name if transport else None,
        "session_id": selection.session_id,
        "status": selection.status,
        "created_at": selection.created_at,
    }


# CREATE SELECTION

@selection_router.post("/", status_code=201)
def create_selection(
    data: SelectionInput,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    validate_items(
        db,
        data.tour_id,
        data.hotel_id,
        data.transport_id
    )

    selection = TravelSelection(
        client_id=client.id,
        tour_id=data.tour_id,
        hotel_id=data.hotel_id,
        transport_id=data.transport_id,
        status="draft"
    )

    db.add(selection)
    db.commit()
    db.refresh(selection)

    return selection_data(db, selection)


# MY SELECTIONS - PERSONAL CABINET

@selection_router.get("/me/")
def my_selections(
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    selections = (
        db.query(TravelSelection)
        .filter(TravelSelection.client_id == client.id)
        .order_by(
            TravelSelection.created_at.desc(),
            TravelSelection.id.desc()
        )
        .all()
    )

    return [
        selection_data(db, item)
        for item in selections
    ]


# SELECTION DETAIL

@selection_router.get("/{selection_id}/")
def detail_selection(
    selection_id: int,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    selection = get_selection(
        db,
        selection_id,
        client.id
    )

    return selection_data(db, selection)


# UPDATE SELECTION

@selection_router.patch("/{selection_id}/")
def update_selection(
    selection_id: int,
    data: SelectionUpdate,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    selection = get_selection(
        db,
        selection_id,
        client.id
    )

    if selection.status != "draft" or selection.session_id:
        raise HTTPException(
            status_code=409,
            detail="Поездка уже передана в чат. Создайте новую поездку"
        )

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Нет данных для изменения"
        )

    tour_id = changes.get(
        "tour_id",
        selection.tour_id
    )

    hotel_id = changes.get(
        "hotel_id",
        selection.hotel_id
    )

    transport_id = changes.get(
        "transport_id",
        selection.transport_id
    )

    validate_items(
        db,
        tour_id,
        hotel_id,
        transport_id
    )

    for key, value in changes.items():
        setattr(selection, key, value)

    db.commit()
    db.refresh(selection)

    return selection_data(db, selection)


# START AI CHAT

@selection_router.post("/{selection_id}/start-chat/")
def start_selection_chat(
    selection_id: int,
    client: ChatClient = Depends(current_client),
    db: Session = Depends(get_db)
):
    selection = get_selection(
        db,
        selection_id,
        client.id
    )

    # Эгер чат мурда ачылган болсо
    if selection.session_id:
        session = db.get(
            ChatSession,
            selection.session_id
        )

        if not session or session.client_id != client.id:
            raise HTTPException(
                status_code=409,
                detail="Связанный чат недоступен"
            )

        return {
            "selection_id": selection.id,
            "session_id": session.id,
            "existing": True,
            "stage": session.stage,
        }

    if selection.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Поездка уже находится в обработке"
        )

    validate_items(
        db,
        selection.tour_id,
        selection.hotel_id,
        selection.transport_id
    )

    data = selection_data(db, selection)

    choices = []

    if data["tour_name"]:
        choices.append(
            f'🏔 Тур: {data["tour_name"]}'
        )

    if data["hotel_name"]:
        choices.append(
            f'🏨 Отель: {data["hotel_name"]}'
        )

    if data["transport_name"]:
        choices.append(
            f'🚗 Транспорт: {data["transport_name"]}'
        )

    # Клиенттин тандаган кызматтары
    selection_message = (
        "Мои выбранные услуги:\n"
        + "\n".join(choices)
    )

    # AI саламдашуусу
    welcome = (
        "Здравствуйте! 👋 Добро пожаловать в KyrgyzGo!\n"
        "Я вижу ваши выбранные услуги.\n"
        "На какую дату планируете поездку "
        "и сколько человек будет путешествовать?"
    )

    session_id = str(uuid.uuid4())

    session = ChatSession(
        id=session_id,
        client_id=client.id,
        state={
            "tour_id": selection.tour_id,
            "hotel_id": selection.hotel_id,
            "transport_id": selection.transport_id,
        },
        revision=0,
        stage="consultation"
    )

    db.add(session)
    db.flush()

    # Биринчи билдирүү - клиенттин тандоосу
    db.add(
        ChatMessage(
            session_id=session_id,
            role="user",
            content=selection_message
        )
    )

    # Экинчи билдирүү - AI саламдашуусу
    db.add(
        ChatMessage(
            session_id=session_id,
            role="assistant",
            content=welcome
        )
    )

    selection.session_id = session_id

    db.commit()

    return {
        "selection_id": selection.id,
        "session_id": session_id,
        "selection_message": selection_message,
        "welcome": welcome,
        "existing": False,
    }
