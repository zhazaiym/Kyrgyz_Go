
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Transport
from mysite.database.schema import (
    TransportInputSchema,
    TransportUpdateSchema,
    TransportOutSchema
)


transport_router = APIRouter(
    prefix="/transports",
    tags=["Transports"]
)


@transport_router.post("/", response_model=TransportOutSchema)
def create_transport(
    transport: TransportInputSchema,
    db: Session = Depends(get_db)
):
    transport_db = Transport(**transport.model_dump())

    db.add(transport_db)
    db.commit()
    db.refresh(transport_db)

    return transport_db


@transport_router.get("/", response_model=list[TransportOutSchema])
def list_transports(
    db: Session = Depends(get_db)
):
    return db.query(Transport).all()


@transport_router.get("/{transport_id}/", response_model=TransportOutSchema)
def detail_transport(
    transport_id: int,
    db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None:
        raise HTTPException(
            status_code=404,
            detail="Транспорт табылган жок"
        )

    return transport_db


@transport_router.put("/{transport_id}/", response_model=TransportOutSchema)
def update_transport(
    transport_id: int,
    transport: TransportUpdateSchema,
    db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None:
        raise HTTPException(
            status_code=404,
            detail="Транспорт табылган жок"
        )

    data = transport.model_dump(exclude_unset=True)

    for field in ("name", "seats", "price"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=400,
                detail=f"{field} бош болбошу керек"
            )

    for key, value in data.items():
        setattr(transport_db, key, value)

    db.commit()
    db.refresh(transport_db)

    return transport_db


@transport_router.delete("/{transport_id}/")
def delete_transport(
    transport_id: int,
    db: Session = Depends(get_db)
):
    transport_db = db.get(Transport, transport_id)

    if transport_db is None:
        raise HTTPException(
            status_code=404,
            detail="Транспорт табылган жок"
        )

    db.delete(transport_db)
    db.commit()

    return {
        "message": "Транспорт өчүрүлдү"
    }
