from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict

from mysite.database.models import (
    PriceUnitChoices,
    RequestStatusChoices,
    TourTypeChoices
)

class AdminInputSchema(BaseModel):
    username: str
    password: str
    is_active: bool = True

class AdminLoginSchema(BaseModel):
    username: str
    password: str


class AdminUpdateSchema(BaseModel):
    username: str | None = None
    password: str | None = None
    is_active: bool | None = None


class AdminOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    created_at: datetime

class TokenSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"

class AboutInputSchema(BaseModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    experience_years: int = 6
    travelers_count: int = 28000
    branches_count: int = 3
    destinations_count: int = 20
    routes_count: int = 100
    is_active: bool = True


class AboutUpdateSchema(BaseModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    experience_years: int | None = None
    travelers_count: int | None = None
    branches_count: int | None = None
    destinations_count: int | None = None
    routes_count: int | None = None
    is_active: bool | None = None


class AboutOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    experience_years: int
    travelers_count: int
    branches_count: int
    destinations_count: int
    routes_count: int
    is_active: bool


class AboutSectionInputSchema(BaseModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    order: int = 0
    is_active: bool = True


class AboutSectionUpdateSchema(BaseModel):
    title: str | None = None
    description: str | None = None
    image: str | None = None
    order: int | None = None
    is_active: bool | None = None

class AboutSectionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    order: int
    is_active: bool


class TourCategoryInputSchema(BaseModel):
    name: str
    image: str | None = None


class TourCategoryUpdateSchema(BaseModel):
    name: str | None = None
    image: str | None = None


class TourCategoryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None

class TourInputSchema(BaseModel):
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
    main_image: str | None = None
    is_active: bool = True

class TourUpdateSchema(BaseModel):
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
    main_image: str | None = None
    is_active: bool | None = None


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
    main_image: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TourImageInputSchema(BaseModel):
    tour_id: int
    image: str
    order: int = 0


class TourImageUpdateSchema(BaseModel):
    tour_id: int | None = None
    image: str | None = None
    order: int | None = None


class TourImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tour_id: int
    image: str
    order: int


class TourProgramInputSchema(BaseModel):
    tour_id: int
    day_number: int
    title: str | None = None
    description: str | None = None
    start_time: str | None = None
    end_time: str | None = None

class TourProgramUpdateSchema(BaseModel):
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



class CountryInputSchema(BaseModel):
    name: str


class CountryUpdateSchema(BaseModel):
    name: str | None = None


class CountryOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RegionInputSchema(BaseModel):
    name: str
    image: str | None = None
    country_id: int | None = None


class RegionUpdateSchema(BaseModel):
    name: str | None = None
    image: str | None = None
    country_id: int | None = None


class RegionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image: str | None
    country_id: int | None


class DistrictInputSchema(BaseModel):
    region_id: int
    name: str


class DistrictUpdateSchema(BaseModel):
    region_id: int | None = None
    name: str | None = None


class DistrictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region_id: int
    name: str


class HotelInputSchema(BaseModel):
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


class HotelUpdateSchema(BaseModel):
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


class HotelImageInputSchema(BaseModel):
    hotel_id: int
    image: str
    order: int = 0


class HotelImageUpdateSchema(BaseModel):
    hotel_id: int | None = None
    image: str | None = None
    order: int | None = None


class HotelImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    image: str
    order: int

class TransportInputSchema(BaseModel):
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


class TransportUpdateSchema(BaseModel):
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

class TransportImageInputSchema(BaseModel):
    transport_id: int
    image: str
    order: int = 0


class TransportImageUpdateSchema(BaseModel):
    transport_id: int | None = None
    image: str | None = None
    order: int | None = None


class TransportImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transport_id: int
    image: str
    order: int

class TrekkingProgramInputSchema(BaseModel):
    trekking_id: int
    day_number: int
    start_time: str | None = None
    end_time: str | None = None
    title: str | None = None
    description: str | None = None


class TrekkingProgramUpdateSchema(BaseModel):
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

class ContactInputSchema(BaseModel):
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


class ContactUpdateSchema(BaseModel):
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


class FAQInputSchema(BaseModel):
    question: str
    answer: str
    order: int = 0
    is_active: bool = True


class FAQUpdateSchema(BaseModel):
    question: str | None = None
    answer: str | None = None
    order: int | None = None
    is_active: bool | None = None

class FAQOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    order: int
    is_active: bool


class TravelRequestInputSchema(BaseModel):
    name: str
    phone: str
    email: str | None = None
    travel_date: date | None = None
    duration_days: int | None = None
    travelers_count: int | None = None
    destination: str | None = None
    message: str | None = None
    status: RequestStatusChoices = RequestStatusChoices.new


class TravelRequestUpdateSchema(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    travel_date: date | None = None
    duration_days: int | None = None
    travelers_count: int | None = None
    destination: str | None = None
    message: str | None = None
    status: RequestStatusChoices | None = None

class TravelRequestOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

class HelicopterTourInputSchema(BaseModel):
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


class HelicopterTourUpdateSchema(BaseModel):
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


from pydantic import Field

class TransportDetailSchema(TransportOutSchema):
    images: list[TransportImageOutSchema] = Field(default_factory=list)

class HelicopterImageInputSchema(BaseModel):
    helicopter_id: int
    image: str
    order: int = 0



class HelicopterImageUpdateSchema(BaseModel):
    helicopter_id: int | None = None
    image: str | None = None
    order: int | None = None


class HelicopterImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    helicopter_id: int
    image: str
    order: int

class HelicopterTourDetailSchema(HelicopterTourOutSchema):
    images: list[HelicopterImageOutSchema] = Field(default_factory=list)

class TrekkingInputSchema(BaseModel):
    title: str
    description: str | None = None
    price: Decimal
    price_unit: PriceUnitChoices = PriceUnitChoices.per_person
    duration_days: int | None = None
    main_image: str | None = None
    is_active: bool = True


class TrekkingUpdateSchema(BaseModel):
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


class TrekkingImageInputSchema(BaseModel):
    trekking_id: int
    image: str
    order: int = 0


class TrekkingImageUpdateSchema(BaseModel):
    trekking_id: int | None = None
    image: str | None = None
    order: int | None = None


class TrekkingImageOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trekking_id: int
    image: str
    order: int

class TrekkingDetailSchema(TrekkingOutSchema):
    images: list[TrekkingImageOutSchema] = Field(default_factory=list)
    programs: list[TrekkingProgramOutSchema] = Field(default_factory=list)

class RegionDetailSchema(RegionOutSchema):
    districts: list[DistrictOutSchema] = Field(default_factory=list)


