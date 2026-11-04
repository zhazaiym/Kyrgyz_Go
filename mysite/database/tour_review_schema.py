from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TourReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)

    @field_validator('text')
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Review text cannot be empty')
        return value


class TourReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rating: int
    text: str
    created_at: datetime
