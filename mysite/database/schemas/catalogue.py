from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from mysite.database.models import PriceUnitChoices, TourTypeChoices


class TourCategoryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None


class TourOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int | None
    title: str
    description: str | None
    included: str | None
    excluded: str | None
    price: Decimal
    price_unit: PriceUnitChoices
    duration_days: int | None
    duration_nights: int | None
    min_people: int
    max_people: int | None
    tour_type: TourTypeChoices
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    main_image: str | None
    video_url: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    country_id: int | None = Field(default=None, gt=0)


class TourImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    image: str
    order: int


class TourProgramOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    day_number: int
    title: str | None
    description: str | None
    start_time: str | None
    end_time: str | None


class CountryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RegionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None
    country_id: int | None


class DistrictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    name: str


class HotelOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    district_id: int
    name: str
    description: str | None
    address: str | None
    price: Decimal
    price_unit: PriceUnitChoices
    stars: int | None
    phone: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    amenities: list | None
    main_image: str | None
    is_active: bool
    created_at: datetime


class HotelImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    image: str
    order: int


class TransportOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    model: str | None
    color: str | None
    year: int | None
    seats: int
    description: str | None
    price: Decimal
    price_unit: PriceUnitChoices
    has_driver: bool
    has_air_conditioner: bool
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    main_image: str | None
    is_active: bool
    created_at: datetime


class TransportImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transport_id: int
    image: str
    order: int


class TrekkingProgramOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trekking_id: int
    day_number: int
    start_time: str | None
    end_time: str | None
    title: str | None
    description: str | None


class TourVideoOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    video_url: str
    poster_url: str | None
    order: int


class TourDetailSchema(TourOutSchema):
    videos: list[TourVideoOutSchema] = Field(default_factory=list)
    images: list[TourImageOutSchema] = []
    programs: list[TourProgramOutSchema] = []


class HelicopterTourOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    price: Decimal
    duration_minutes: int | None = None
    max_passengers: int | None = None
    departure_location: str | None = None
    destination: str | None = None
    main_image: str | None = None


class HelicopterImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    helicopter_id: int
    image: str
    order: int


class TrekkingOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    price: Decimal
    price_unit: PriceUnitChoices
    duration_days: int | None
    main_image: str | None
    is_active: bool


class TrekkingImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trekking_id: int
    image: str
    order: int
