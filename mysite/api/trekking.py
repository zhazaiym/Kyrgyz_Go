
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.database.models import Trekking
from mysite.database.schema import (
    TrekkingInputSchema,
    TrekkingUpdateSchema,
    TrekkingOutSchema
)


trekking_router = APIRouter(
    prefix="/trekkings",
    tags=["Trekking"]
)


@trekking_router.post("/", response_model=TrekkingOutSchema, dependencies=[Depends(get_current_admin)])
def create_trekking(
    trekking: TrekkingInputSchema,
    db: Session = Depends(get_db)
):
    trekking_db = Trekking(**trekking.model_dump())

    db.add(trekking_db)
    db.commit()
    db.refresh(trekking_db)

    return trekking_db


@trekking_router.get("/", response_model=list[TrekkingOutSchema])
def list_trekkings(db: Session = Depends(get_db)):
    return db.query(Trekking).all()


@trekking_router.get("/{trekking_id}/", response_model=TrekkingOutSchema)
def detail_trekking(
    trekking_id: int,
    db: Session = Depends(get_db)
):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None:
        raise HTTPException(
            status_code=404,
            detail="Треккинг табылган жок"
        )

    return trekking_db


@trekking_router.put("/{trekking_id}/", response_model=TrekkingOutSchema, dependencies=[Depends(get_current_admin)])
def update_trekking(
    trekking_id: int,
    trekking: TrekkingUpdateSchema,
    db: Session = Depends(get_db)
):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None:
        raise HTTPException(
            status_code=404,
            detail="Треккинг табылган жок"
        )

    data = trekking.model_dump(exclude_unset=True)

    for field in ("title", "price", "price_unit", "is_active"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=400,
                detail=f"{field} бош болбошу керек"
            )

    for key, value in data.items():
        setattr(trekking_db, key, value)

    db.commit()
    db.refresh(trekking_db)

    return trekking_db


@trekking_router.delete("/{trekking_id}/", dependencies=[Depends(get_current_admin)])
def delete_trekking(
    trekking_id: int,
    db: Session = Depends(get_db)
):
    trekking_db = db.get(Trekking, trekking_id)

    if trekking_db is None:
        raise HTTPException(
            status_code=404,
            detail="Треккинг табылган жок"
        )

    db.delete(trekking_db)
    db.commit()

    return {"message": "Треккинг өчүрүлдү"}
