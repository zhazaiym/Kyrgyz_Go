from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mysite.database.input_validation import StorageInput
from mysite.database.models import RequestStatusChoices


class TravelRequestUpdateSchema(StorageInput):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    travel_date: date | None = None
    duration_days: int | None = None
    travelers_count: int | None = None
    destination: str | None = None
    message: str | None = None
    status: RequestStatusChoices | None = None


class SelectedServiceSchema(BaseModel):
    kind: Literal['tour', 'hotel', 'transport']
    id: int
    name: str


class TravelRequestOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    selected_services: list[SelectedServiceSchema] | None = None

    id: int
    name: str
    phone: str
    email: str | None
    travel_date: date | None
    duration_days: int | None
    travelers_count: int | None
    destination: str | None
    message: str | None
    status: RequestStatusChoices
    created_at: datetime
