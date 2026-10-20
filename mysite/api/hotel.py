
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Hotel, Region, District
from mysite.database.schema import (
    HotelInputSchema,
    HotelUpdateSchema,
    HotelOutSchema
)


hotel_router = APIRouter(
    prefix="/hotels",
    tags=["Hotels"]
)


def check_location(db, region_id, district_id):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(
            status_code=404,
            detail="Район табылган жок"
        )

    if district_db.region_id != region_id:
        raise HTTPException(
            status_code=400,
            detail="Район бул областька тиешелүү эмес"
        )


@hotel_router.post("/", response_model=HotelOutSchema)
def create_hotel(
    hotel: HotelInputSchema,
    db: Session = Depends(get_db)
):
    check_location(
        db,
        hotel.region_id,
        hotel.district_id
    )

    hotel_db = Hotel(**hotel.model_dump())

    db.add(hotel_db)
    db.commit()
    db.refresh(hotel_db)

    return hotel_db


@hotel_router.get("/", response_model=list[HotelOutSchema])
def list_hotels(
    db: Session = Depends(get_db)
):
    return db.query(Hotel).all()


@hotel_router.get("/{hotel_id}/", response_model=HotelOutSchema)
def detail_hotel(
    hotel_id: int,
    db: Session = Depends(get_db)
):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None:
        raise HTTPException(
            status_code=404,
            detail="Мейманкана табылган жок"
        )

    return hotel_db


@hotel_router.put("/{hotel_id}/", response_model=HotelOutSchema)
def update_hotel(
    hotel_id: int,
    hotel: HotelUpdateSchema,
    db: Session = Depends(get_db)
):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None:
        raise HTTPException(
            status_code=404,
            detail="Мейманкана табылган жок"
        )

    data = hotel.model_dump(exclude_unset=True)

    region_id = data.get(
        "region_id",
        hotel_db.region_id
    )

    district_id = data.get(
        "district_id",
        hotel_db.district_id
    )

    if region_id is None or district_id is None:
        raise HTTPException(
            status_code=400,
            detail="Область жана район милдеттүү"
        )

    check_location(
        db,
        region_id,
        district_id
    )

    for key, value in data.items():
        setattr(hotel_db, key, value)

    db.commit()
    db.refresh(hotel_db)

    return hotel_db


@hotel_router.delete("/{hotel_id}/")
def delete_hotel(
    hotel_id: int,
    db: Session = Depends(get_db)
):
    hotel_db = db.get(Hotel, hotel_id)

    if hotel_db is None:
        raise HTTPException(
            status_code=404,
            detail="Мейманкана табылган жок"
        )

    db.delete(hotel_db)
    db.commit()

    return {
        "message": "Мейманкана өчүрүлдү"
    }
