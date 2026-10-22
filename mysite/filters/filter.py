from decimal import Decimal
from fastapi_filter.contrib.sqlalchemy import Filter
from pydantic import Field, model_validator
from sqlalchemy import or_

from mysite.database.models import (Tour, Hotel, Transport, Trekking, HelicopterTour,
                                    Region, District, TourCategory, Country, PriceUnitChoices, TourTypeChoices)


class PriceFilter(Filter):
    price__gte: Decimal | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    price__lte: Decimal | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    price_unit: PriceUnitChoices | None = None

    search: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )

    order_by: list[str] | None = None

    @model_validator(mode="after")
    def check_ranges(self):
        for name in type(self).model_fields:
            if not name.endswith("__gte"):
                continue

            upper_name = name.removesuffix("__gte") + "__lte"

            if upper_name not in type(self).model_fields:
                continue

            lower = getattr(self, name)
            upper = getattr(self, upper_name)

            if (
                lower is not None
                and upper is not None
                and lower > upper
            ):
                raise ValueError(
                    f"{name} не должен быть больше {upper_name}"
                )

        return self




class TourFilter(PriceFilter):
    country_id: int | None = Field(None, gt=0)
    category_id: int | None = Field(None, gt=0)

    tour_type: TourTypeChoices | None = None

    duration_days__gte: int | None = Field(None, ge=1)
    duration_days__lte: int | None = Field(None, ge=1)

    guests: int | None = Field(None, ge=1)

    class Constants(Filter.Constants):
        model = Tour
        search_model_fields = ["title"]

    def filter(self, query):
        # guests — өзүнчө шарт, Tour таблицасындагы талаа эмес.
        standard_filter = self.model_copy(
            update={"guests": None}
        )

        query = super(
            TourFilter, standard_filter
        ).filter(query)

        if self.guests is not None:
            query = query.filter(
                Tour.min_people <= self.guests,
                or_(
                    Tour.max_people.is_(None),
                    Tour.max_people >= self.guests,
                ),
            )

        return query


class HotelFilter(PriceFilter):
    region_id: int | None = Field(None, gt=0)
    district_id: int | None = Field(None, gt=0)

    stars: int | None = Field(None, ge=1, le=5)
    stars__gte: int | None = Field(None, ge=1, le=5)
    stars__lte: int | None = Field(None, ge=1, le=5)

    class Constants(Filter.Constants):
        model = Hotel
        search_model_fields = [
            "name",
            "description",
            "address",
        ]



class TransportFilter(PriceFilter):
    brand: str | None = None
    model: str | None = None

    seats__gte: int | None = Field(None, ge=1)
    seats__lte: int | None = Field(None, ge=1)

    has_driver: bool | None = None
    has_air_conditioner: bool | None = None

    class Constants(Filter.Constants):
        model = Transport
        search_model_fields = [
            "name",
            "brand",
            "model",
            "description",
        ]



class TrekkingFilter(PriceFilter):
    difficulty: str | None = None

    duration_days__gte: int | None = Field(None, ge=1)
    duration_days__lte: int | None = Field(None, ge=1)

    distance_km__gte: Decimal | None = Field(None, ge=0, allow_inf_nan=False)
    distance_km__lte: Decimal | None = Field(None, ge=0, allow_inf_nan=False)

    class Constants(Filter.Constants):
        model = Trekking
        search_model_fields = ["title", "description", "route"]


class HelicopterTourFilter(PriceFilter):
    destination: str | None = None
    departure_location: str | None = None

    duration_minutes__gte: int | None = Field(None, ge=1)
    duration_minutes__lte: int | None = Field(None, ge=1)

    max_passengers__gte: int | None = Field(None, ge=1)

    class Constants(Filter.Constants):
        model = HelicopterTour
        search_model_fields = ["title", "description", "destination", "departure_location"]



class RegionFilter(Filter):
    country_id: int | None = Field(None, gt=0)

    search: str | None = Field(None, min_length=1, max_length=200)
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
        model = Region
        search_model_fields = ["name"]


class DistrictFilter(Filter):
    region_id: int | None = Field(None, gt=0)

    search: str | None = Field(None, min_length=1, max_length=200)
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
        model = District
        search_model_fields = ["name"]