from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


def _clipped(limit):
    """A longer value is cut, not rejected: one long field must not void the whole extraction.

    The limit stays out of the JSON schema sent to Gemini, which accepts only a
    subset of schema keywords.
    """
    return AfterValidator(lambda value: value if value is None else value[:limit])


class Changes(BaseModel):
    language: Literal['ru', 'ky', 'en', 'de', 'zh'] | None = None
    client_name: Annotated[str | None, _clipped(255)] = None
    phone: Annotated[str | None, _clipped(32)] = None
    email: Annotated[str | None, _clipped(254)] = None
    tour_id: int | None = None
    destination: Annotated[str | None, _clipped(255)] = None
    travel_date: Annotated[str | None, _clipped(10)] = Field(
        default=None, description='Unambiguous YYYY-MM-DD'
    )
    duration_days: int | None = Field(default=None, ge=1)
    people_count: int | None = Field(default=None, ge=1)
    budget: Annotated[str | None, _clipped(200)] = None
    notes: Annotated[str | None, _clipped(1500)] = None
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


class FieldTranslation(BaseModel):
    field: str
    text: str


class Translations(BaseModel):
    """One shape for every table: the translated fields are listed by name per language."""

    en: list[FieldTranslation]
    de: list[FieldTranslation]
    zh: list[FieldTranslation]
