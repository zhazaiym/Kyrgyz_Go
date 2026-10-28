from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mysite.database.contact_validation import validate_whatsapp_link
from mysite.database.input_validation import StorageInput
from mysite.database.models import PriceUnitChoices, RequestStatusChoices, TourTypeChoices


class AdminLoginSchema(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class AdminOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    created_at: datetime


class TokenSchema(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class AboutInputSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    is_active: bool = True


class AboutUpdateSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    is_active: bool | None = None


class AboutOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    is_active: bool


class AboutSectionInputSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    is_active: bool = True


class AboutSectionUpdateSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    is_active: bool | None = None


class AboutSectionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    order: int
    is_active: bool


class TourCategoryInputSchema(StorageInput):
    name: str
    image: str | None = None


class TourCategoryUpdateSchema(StorageInput):
    name: str | None = None
    image: str | None = None


class TourCategoryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None


class TourInputSchema(StorageInput):
    category_id: int | None = None
    title: str
    description: str | None = None
    included: str | None = None
    excluded: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_person
    duration_days: int | None = None
    duration_nights: int | None = None
    min_people: int = 1
    max_people: int | None = None
    tour_type: TourTypeChoices = TourTypeChoices.classic
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    main_image: str | None = None
    is_active: bool = True
    country_id: int | None = Field(default=None, gt=0)


class TourUpdateSchema(StorageInput):
    category_id: int | None = None
    title: str | None = None
    description: str | None = None
    included: str | None = None
    excluded: str | None = None
    price: Decimal | None = None
    price_unit: PriceUnitChoices | None = None
    duration_days: int | None = None
    duration_nights: int | None = None
    min_people: int | None = None
    max_people: int | None = None
    tour_type: TourTypeChoices | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    main_image: str | None = None
    is_active: bool | None = None
    country_id: int | None = Field(default=None, gt=0)


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
    is_active: bool
    created_at: datetime
    updated_at: datetime
    country_id: int | None = Field(default=None, gt=0)


class TourImageInputSchema(StorageInput):
    tour_id: int
    image: str
    order: int = 0


class TourImageUpdateSchema(StorageInput):
    tour_id: int | None = None
    image: str | None = None
    order: int | None = None


class TourImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    image: str
    order: int


class TourProgramInputSchema(StorageInput):
    tour_id: int
    day_number: int
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class TourProgramUpdateSchema(StorageInput):
    tour_id: int | None = None
    day_number: int | None = None
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None


class TourProgramOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    day_number: int
    title: str | None
    description: str | None
    start_time: str | None
    end_time: str | None


class CountryInputSchema(StorageInput):
    name: str


class CountryUpdateSchema(StorageInput):
    name: str | None = None


class CountryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RegionInputSchema(StorageInput):
    name: str
    image: str | None = None
    country_id: int | None = None


class RegionUpdateSchema(StorageInput):
    name: str | None = None
    image: str | None = None
    country_id: int | None = None


class RegionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None
    country_id: int | None


class DistrictInputSchema(StorageInput):
    region_id: int
    name: str


class DistrictUpdateSchema(StorageInput):
    region_id: int | None = None
    name: str | None = None


class DistrictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    name: str


class HotelInputSchema(StorageInput):
    region_id: int
    district_id: int
    name: str
    description: str | None = None
    address: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_night
    stars: int | None = None
    phone: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    amenities: list | None = None
    main_image: str | None = None
    is_active: bool = True


class HotelUpdateSchema(StorageInput):
    region_id: int | None = None
    district_id: int | None = None
    name: str | None = None
    description: str | None = None
    address: str | None = None
    price: Decimal | None = None
    price_unit: PriceUnitChoices | None = None
    stars: int | None = None
    phone: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    amenities: list | None = None
    main_image: str | None = None
    is_active: bool | None = None


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


class HotelImageInputSchema(StorageInput):
    hotel_id: int
    image: str
    order: int = 0


class HotelImageUpdateSchema(StorageInput):
    hotel_id: int | None = None
    image: str | None = None
    order: int | None = None


class HotelImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    image: str
    order: int


class TransportInputSchema(StorageInput):
    name: str
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    seats: int
    description: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_day
    has_driver: bool = True
    has_air_conditioner: bool = True
    main_image: str | None = None
    is_active: bool = True


class TransportUpdateSchema(StorageInput):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    seats: int | None = None
    description: str | None = None
    price: Decimal | None = None
    price_unit: PriceUnitChoices | None = None
    has_driver: bool | None = None
    has_air_conditioner: bool | None = None
    main_image: str | None = None
    is_active: bool | None = None


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
    main_image: str | None
    is_active: bool
    created_at: datetime


class TransportImageInputSchema(StorageInput):
    transport_id: int
    image: str
    order: int = 0


class TransportImageUpdateSchema(StorageInput):
    transport_id: int | None = None
    image: str | None = None
    order: int | None = None


class TransportImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transport_id: int
    image: str
    order: int


class TrekkingProgramInputSchema(StorageInput):
    trekking_id: int
    day_number: int
    start_time: str | None = None
    end_time: str | None = None
    title: str | None = None
    description: str | None = None


class TrekkingProgramUpdateSchema(StorageInput):
    trekking_id: int | None = None
    day_number: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    title: str | None = None
    description: str | None = None


class TrekkingProgramOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trekking_id: int
    day_number: int
    start_time: str | None
    end_time: str | None
    title: str | None
    description: str | None


class ContactInputSchema(StorageInput):
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    telegram: str | None = None
    address: str | None = None
    qr_code: str | None = None
    is_active: bool = True

    _validate_whatsapp = field_validator('whatsapp')(validate_whatsapp_link)


class ContactUpdateSchema(StorageInput):
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    instagram: str | None = None
    facebook: str | None = None
    telegram: str | None = None
    address: str | None = None
    qr_code: str | None = None
    is_active: bool | None = None

    _validate_whatsapp = field_validator('whatsapp')(validate_whatsapp_link)


class ContactOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    country: str | None
    city: str | None
    phone: str | None
    whatsapp: str | None
    email: str | None
    instagram: str | None
    facebook: str | None
    telegram: str | None
    address: str | None
    qr_code: str | None
    is_active: bool


class FAQInputSchema(StorageInput):
    question: str
    answer: str
    is_active: bool = True


class FAQUpdateSchema(StorageInput):
    question: str | None = None
    answer: str | None = None
    is_active: bool | None = None


class FAQOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    order: int
    is_active: bool


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


class TourDetailSchema(TourOutSchema):
    images: list[TourImageOutSchema] = []
    programs: list[TourProgramOutSchema] = []


class HelicopterTourInputSchema(StorageInput):
    title: str
    description: str | None = None
    destination: str | None = None
    instruction: str | None = None
    included: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_trip
    duration_minutes: int | None = None
    max_passengers: int | None = None
    departure_location: str | None = None
    main_image: str | None = None
    is_active: bool = True


class HelicopterTourUpdateSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    destination: str | None = None
    instruction: str | None = None
    included: str | None = None
    price: Decimal | None = None
    price_unit: PriceUnitChoices | None = None
    duration_minutes: int | None = None
    max_passengers: int | None = None
    departure_location: str | None = None
    main_image: str | None = None
    is_active: bool | None = None


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


class HelicopterImageInputSchema(StorageInput):
    helicopter_id: int
    image: str
    order: int = 0


class HelicopterImageUpdateSchema(StorageInput):
    helicopter_id: int | None = None
    image: str | None = None
    order: int | None = None


class HelicopterImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    helicopter_id: int
    image: str
    order: int


class TrekkingInputSchema(StorageInput):
    title: str
    description: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_person
    duration_days: int | None = None
    main_image: str | None = None
    is_active: bool = True


class TrekkingUpdateSchema(StorageInput):
    title: str | None = None
    description: str | None = None
    price: Decimal | None = None
    price_unit: PriceUnitChoices | None = None
    duration_days: int | None = None
    main_image: str | None = None
    is_active: bool | None = None


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


class TrekkingImageInputSchema(StorageInput):
    trekking_id: int
    image: str
    order: int = 0


class TrekkingImageUpdateSchema(StorageInput):
    trekking_id: int | None = None
    image: str | None = None
    order: int | None = None


class TrekkingImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trekking_id: int
    image: str
    order: int
