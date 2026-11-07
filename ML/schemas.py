from typing import Literal

from pydantic import BaseModel, Field


class Changes(BaseModel):
    language: Literal['ru', 'ky', 'en', 'de', 'zh'] | None = None
    client_name: str | None = None
    phone: str | None = None
    email: str | None = None
    tour_id: int | None = None
    destination: str | None = None
    travel_date: str | None = Field(default=None, description='Unambiguous YYYY-MM-DD')
    duration_days: int | None = Field(default=None, ge=1)
    people_count: int | None = Field(default=None, ge=1)
    budget: str | None = None
    notes: str | None = None
    clear_fields: list[
        Literal[
            'client_name',
            'phone',
            'email',
            'tour_id',
            'destination',
            'travel_date',
            'duration_days',
            'people_count',
            'budget',
            'notes',
        ]
    ] = Field(default_factory=list)
    booking_intent: bool = False
