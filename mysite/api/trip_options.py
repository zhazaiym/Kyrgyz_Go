"""Step-by-step trip building: after a tour, offer only suitable, nearest options.

Step 1 — the client picks a tour.
Step 2 — hotels: active hotels near the tour (great-circle distance from the
         tour coordinates, within ``TRIP_OPTION_RADIUS_KM``), nearest first.
         A tour without coordinates falls back to hotels of the tour country.
Step 3 — transport: active vehicles with enough seats for the group, nearest
         base first; vehicles without a known base come after located ones.
"""

import math
import os
from dataclasses import dataclass
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from mysite.api.errors import error_detail
from mysite.database.catalogue_rules import is_demo_name
from mysite.database.db import get_db
from mysite.database.models import Hotel, Region, Tour, Transport
from mysite.translations.content import Language, localized

trip_options_router = APIRouter(prefix='/tours', tags=['Trip options'])

EARTH_RADIUS_KM = 6371.0088
DEFAULT_RADIUS_KM = 100.0
MAX_OPTIONS = 50

HOTEL_CARD_FIELDS = (
    'id',
    'name',
    'price',
    'price_unit',
    'main_image',
    'region_id',
    'district_id',
    'stars',
)
TRANSPORT_CARD_FIELDS = (
    'id',
    'name',
    'seats',
    'price',
    'price_unit',
    'main_image',
    'has_driver',
    'has_air_conditioner',
)


def radius_km() -> float:
    try:
        value = float(os.getenv('TRIP_OPTION_RADIUS_KM', DEFAULT_RADIUS_KM))
    except ValueError:
        return DEFAULT_RADIUS_KM
    return value if 0 < value <= 2000 else DEFAULT_RADIUS_KM


def coordinates(record) -> tuple[float, float] | None:
    if record is None or record.latitude is None or record.longitude is None:
        return None
    return float(record.latitude), float(record.longitude)


def distance_km(origin, target) -> float:
    lat1, lon1 = map(math.radians, origin)
    lat2, lon2 = map(math.radians, target)
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bounding_box(query, model, origin, radius):
    """Cheap SQL prefilter; the exact distance is checked afterwards."""
    lat, lon = origin
    lat_delta = radius / 111.0
    lon_delta = radius / max(1e-6, 111.0 * math.cos(math.radians(lat)))
    return query.filter(
        model.latitude.between(Decimal(str(lat - lat_delta)), Decimal(str(lat + lat_delta))),
        model.longitude.between(Decimal(str(lon - lon_delta)), Decimal(str(lon + lon_delta))),
    )


def visible(record, name_field='name') -> bool:
    return bool(record.is_active) and not is_demo_name(getattr(record, name_field))


def active_tour(db: Session, tour_id: int) -> Tour:
    tour = db.get(Tour, tour_id)
    if tour is None or not visible(tour, 'title'):
        raise HTTPException(404, error_detail('not_found'))
    return tour


@dataclass
class Option:
    record: object
    distance: float | None


def hotel_options(db: Session, tour: Tour) -> tuple[str, list[Option]]:
    origin = coordinates(tour)
    query = db.query(Hotel).filter(Hotel.is_active.is_(True))
    if origin is not None:
        radius = radius_km()
        located = bounding_box(
            query.filter(Hotel.latitude.isnot(None), Hotel.longitude.isnot(None)),
            Hotel,
            origin,
            radius,
        ).all()
        options = [Option(hotel, distance_km(origin, coordinates(hotel))) for hotel in located]
        options = [item for item in options if item.distance <= radius and visible(item.record)]
        options.sort(key=lambda item: (item.distance, item.record.price, item.record.id))
        return 'distance', options
    if tour.country_id is not None:
        query = query.join(Region, Hotel.region_id == Region.id).filter(
            Region.country_id == tour.country_id
        )
        basis = 'country'
    else:
        basis = 'any'
    hotels = [hotel for hotel in query.all() if visible(hotel)]
    hotels.sort(key=lambda hotel: (hotel.price, hotel.id))
    return basis, [Option(hotel, None) for hotel in hotels]


def group_size(tour: Tour, travelers: int | None) -> int:
    needed = travelers if travelers is not None else (tour.min_people or 1)
    if tour.max_people is not None and needed > tour.max_people:
        raise HTTPException(422, error_detail('invalid_travelers_count'))
    return max(needed, 1)


def transport_options(db: Session, tour: Tour, travelers: int | None) -> list[Option]:
    needed = group_size(tour, travelers)
    origin = coordinates(tour)
    radius = radius_km()
    vehicles = (
        db.query(Transport).filter(Transport.is_active.is_(True), Transport.seats >= needed).all()
    )
    located, unknown = [], []
    for vehicle in vehicles:
        if not visible(vehicle):
            continue
        base = coordinates(vehicle)
        if origin is None or base is None:
            unknown.append(Option(vehicle, None))
            continue
        distance = distance_km(origin, base)
        if distance <= radius:
            located.append(Option(vehicle, distance))
    located.sort(key=lambda item: (item.distance, item.record.seats, item.record.price))
    # Smallest vehicle that still fits the group first, then cheaper.
    unknown.sort(key=lambda item: (item.record.seats, item.record.price, item.record.id))
    return located + unknown


def card(option: Option, fields, lang: Language):
    data = localized(option.record, lang)
    result = {key: data[key] for key in fields}
    result['distance_km'] = None if option.distance is None else round(option.distance, 1)
    return result


def hotel_step(db: Session, tour: Tour, lang: Language, limit: int):
    basis, options = hotel_options(db, tour)
    return {
        'step': 'hotel',
        'tour_id': tour.id,
        'basis': basis,
        'radius_km': radius_km() if basis == 'distance' else None,
        'items': [card(item, HOTEL_CARD_FIELDS, lang) for item in options[:limit]],
    }


def transport_step(db: Session, tour: Tour, travelers: int | None, lang: Language, limit: int):
    options = transport_options(db, tour, travelers)
    return {
        'step': 'transport',
        'tour_id': tour.id,
        'travelers': group_size(tour, travelers),
        'radius_km': radius_km() if coordinates(tour) else None,
        'items': [card(item, TRANSPORT_CARD_FIELDS, lang) for item in options[:limit]],
    }


def check_suitable(db: Session, tour_id, hotel_id, transport_id):
    """Reject a hotel or vehicle that the steps would not offer for this tour."""
    if tour_id is None or (hotel_id is None and transport_id is None):
        return
    tour = db.get(Tour, tour_id)
    if tour is None:
        return
    if hotel_id is not None:
        _, options = hotel_options(db, tour)
        if hotel_id not in {item.record.id for item in options}:
            raise HTTPException(422, error_detail('unsuitable_hotel'))
    if transport_id is not None:
        options = transport_options(db, tour, None)
        if transport_id not in {item.record.id for item in options}:
            raise HTTPException(422, error_detail('unsuitable_transport'))


@trip_options_router.get('/{tour_id}/hotel-options/')
def tour_hotel_options(
    tour_id: int,
    lang: Language = 'ru',
    limit: int = Query(default=10, ge=1, le=MAX_OPTIONS),
    db: Session = Depends(get_db),
):
    return hotel_step(db, active_tour(db, tour_id), lang, limit)


@trip_options_router.get('/{tour_id}/transport-options/')
def tour_transport_options(
    tour_id: int,
    travelers: int | None = Query(default=None, ge=1, le=500),
    lang: Language = 'ru',
    limit: int = Query(default=10, ge=1, le=MAX_OPTIONS),
    db: Session = Depends(get_db),
):
    return transport_step(db, active_tour(db, tour_id), travelers, lang, limit)
