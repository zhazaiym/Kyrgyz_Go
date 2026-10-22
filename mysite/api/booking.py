from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import RequestStatusChoices, Tour, TravelRequest


booking_router = APIRouter(prefix="/bookings", tags=["Bookings"])


class BookingInputSchema(BaseModel):
    tour_id: int
    name: str
    phone: str
    email: str | None = None
    travel_date: date | None = None
    travelers_count: int = Field(default=1, ge=1)
    message: str | None = None


@booking_router.post("/")
def create_booking(
    booking: BookingInputSchema,
    db: Session = Depends(get_db),
):
    tour_db = db.get(Tour, booking.tour_id)
    if tour_db is None:
        raise HTTPException(status_code=404, detail="Тур табылган жок")
    if not tour_db.is_active:
        raise HTTPException(
            status_code=400,
            detail="Бул тур азыр жеткиликтүү эмес",
        )

    booking_db = TravelRequest(
        name=booking.name,
        phone=booking.phone,
        email=booking.email,
        travel_date=booking.travel_date,
        travelers_count=booking.travelers_count,
        destination=tour_db.title,
        duration_days=tour_db.duration_days,
        message=booking.message,
        status=RequestStatusChoices.new,
    )
    db.add(booking_db)
    db.commit()
    db.refresh(booking_db)

    return {
        "message": "Брондоо кабыл алынды",
        "booking_id": booking_db.id,
        "chat_id": None,
        "chat_token": None,
        "status": booking_db.status,
    }
