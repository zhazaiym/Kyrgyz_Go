from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from mysite.database.models import PriceUnitChoices, TourTypeChoices
from mysite.database.schema import HelicopterTourOutSchema, TrekkingOutSchema


class CatalogueCardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    price: Decimal
    price_unit: PriceUnitChoices
    main_image: str | None


class TourCardSchema(CatalogueCardSchema):
    title: str
    category_id: int | None
    duration_days: int | None
    duration_nights: int | None
    tour_type: TourTypeChoices


class HotelCardSchema(CatalogueCardSchema):
    name: str
    region_id: int
    district_id: int
    stars: int | None


class TransportCardSchema(CatalogueCardSchema):
    name: str
    seats: int


class TrekkingCardSchema(CatalogueCardSchema):
    title: str
    duration_days: int | None
    duration_hours: int | None
    difficulty: str | None


class HelicopterTourCardSchema(CatalogueCardSchema):
    title: str
    duration_minutes: int | None
    max_passengers: int | None
    departure_location: str | None
    destination: str | None


class HelicopterCatalogueDetailSchema(HelicopterTourOutSchema):
    price_unit: PriceUnitChoices
    instruction: str | None
    included: str | None


class TrekkingCatalogueDetailSchema(TrekkingOutSchema):
    route: str | None
    included: str | None
    requirements: str | None
    duration_hours: int | None
    difficulty: str | None
    distance_km: Decimal | None
    max_altitude: int | None
    min_people: int
    max_people: int | None
