from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mysite.database.db import Base


def now_utc():
    return datetime.now(timezone.utc)


class RequestStatusChoices(str, PyEnum):
    new = "new"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class TourTypeChoices(str, PyEnum):
    classic = "classic"
    adventure = "adventure"
    cultural = "cultural"
    winter = "winter"
    individual = "individual"
    combined = "combined"


class PriceUnitChoices(str, PyEnum):
    per_person = "per_person"
    per_day = "per_day"
    per_night = "per_night"
    per_hour = "per_hour"
    per_trip = "per_trip"

class LocalizedContent:
    translations: Mapped[dict | None] = mapped_column(JSON)


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class About(LocalizedContent, Base):
    __tablename__ = "abouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(500))
    experience_years: Mapped[int] = mapped_column(Integer, default=6)
    travelers_count: Mapped[int] = mapped_column(Integer, default=28000)
    branches_count: Mapped[int] = mapped_column(Integer, default=3)
    destinations_count: Mapped[int] = mapped_column(Integer, default=20)
    routes_count: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class AboutSection(LocalizedContent, Base):
    __tablename__ = "about_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(500))
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TourCategory(LocalizedContent, Base):
    __tablename__ = "tour_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    image: Mapped[str | None] = mapped_column(String(500))
    tours: Mapped[list["Tour"]] = relationship(back_populates="category")


class Tour(Base):
    __tablename__ = "tours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("tour_categories.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    included: Mapped[str | None] = mapped_column(Text)
    excluded: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_unit: Mapped[PriceUnitChoices] = mapped_column(Enum(PriceUnitChoices), default=PriceUnitChoices.per_person)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    duration_nights: Mapped[int | None] = mapped_column(Integer)
    min_people: Mapped[int] = mapped_column(Integer, default=1)
    max_people: Mapped[int | None] = mapped_column(Integer)
    tour_type: Mapped[TourTypeChoices] = mapped_column(Enum(TourTypeChoices), default=TourTypeChoices.classic)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    main_image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    category: Mapped["TourCategory | None"] = relationship(back_populates="tours")
    images: Mapped[list["TourImage"]] = relationship(back_populates="tour", cascade="all, delete-orphan")
    programs: Mapped[list["TourProgram"]] = relationship(back_populates="tour", cascade="all, delete-orphan")
    translations: Mapped[list["TourTranslation"]] = relationship(back_populates="tour", cascade="all, delete-orphan")
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"), nullable=True, index=True)
    country: Mapped["Country | None"] = relationship(back_populates="tours")


class TourTranslation(Base):
    __tablename__ = "tour_translations"
    __table_args__ = (UniqueConstraint("tour_id", "lang", name="uq_tour_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), nullable=False)
    lang: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    included: Mapped[str | None] = mapped_column(Text)
    excluded: Mapped[str | None] = mapped_column(Text)
    tour: Mapped["Tour"] = relationship(back_populates="translations")


class TourImage(Base):
    __tablename__ = "tour_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), nullable=False)
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    tour: Mapped["Tour"] = relationship(back_populates="images")


class TourProgram(LocalizedContent, Base):
    __tablename__ = "tour_programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tour_id: Mapped[int] = mapped_column(ForeignKey("tours.id", ondelete="CASCADE"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[str | None] = mapped_column(String(10))
    end_time: Mapped[str | None] = mapped_column(String(10))
    tour: Mapped["Tour"] = relationship(back_populates="programs")

class Country(LocalizedContent, Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    regions: Mapped[list["Region"]] = relationship(back_populates="country")
    tours: Mapped[list["Tour"]] = relationship(back_populates="country")

class Region(LocalizedContent, Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    image: Mapped[str | None] = mapped_column(String(500))
    country: Mapped["Country | None"] = relationship(back_populates="regions")
    districts: Mapped[list["District"]] = relationship(back_populates="region")
    hotels: Mapped[list["Hotel"]] = relationship(back_populates="region")


class District(LocalizedContent, Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    region: Mapped["Region"] = relationship(back_populates="districts")
    hotels: Mapped[list["Hotel"]] = relationship(back_populates="district")


class Hotel(LocalizedContent, Base):
    __tablename__ = "hotels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), nullable=False)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_unit: Mapped[PriceUnitChoices] = mapped_column(Enum(PriceUnitChoices), default=PriceUnitChoices.per_night)
    stars: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    amenities: Mapped[list | None] = mapped_column(JSON)
    main_image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    region: Mapped["Region"] = relationship(back_populates="hotels")
    district: Mapped["District"] = relationship(back_populates="hotels")
    images: Mapped[list["HotelImage"]] = relationship(back_populates="hotel", cascade="all, delete-orphan")

class HotelImage(Base):
    __tablename__ = "hotel_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), nullable=False)
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    hotel: Mapped["Hotel"] = relationship(back_populates="images")


class Transport(LocalizedContent, Base):
    __tablename__ = "transports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(150))
    model: Mapped[str | None] = mapped_column(String(150))
    color: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[int | None] = mapped_column(Integer)
    seats: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_unit: Mapped[PriceUnitChoices] = mapped_column(Enum(PriceUnitChoices), default=PriceUnitChoices.per_day)
    has_driver: Mapped[bool] = mapped_column(Boolean, default=True)
    has_air_conditioner: Mapped[bool] = mapped_column(Boolean, default=True)
    main_image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    images: Mapped[list["TransportImage"]] = relationship(back_populates="transport", cascade="all, delete-orphan")

class TransportImage(Base):
    __tablename__ = "transport_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transport_id: Mapped[int] = mapped_column(ForeignKey("transports.id", ondelete="CASCADE"), nullable=False)
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    transport: Mapped["Transport"] = relationship(back_populates="images")


class HelicopterTour(LocalizedContent, Base):
    __tablename__ = "helicopter_tours"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(String(255))
    instruction: Mapped[str | None] = mapped_column(Text)
    included: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_unit: Mapped[PriceUnitChoices] = mapped_column(Enum(PriceUnitChoices), default=PriceUnitChoices.per_trip)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    max_passengers: Mapped[int | None] = mapped_column(Integer)
    departure_location: Mapped[str | None] = mapped_column(String(255))
    main_image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    images: Mapped[list["HelicopterImage"]] = relationship(back_populates="helicopter", cascade="all, delete-orphan")

class HelicopterImage(Base):
    __tablename__ = "helicopter_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    helicopter_id: Mapped[int] = mapped_column(ForeignKey("helicopter_tours.id", ondelete="CASCADE"), nullable=False)
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    helicopter: Mapped["HelicopterTour"] = relationship(back_populates="images")


class Trekking(LocalizedContent, Base):
    __tablename__ = "trekkings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(Text)
    included: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_unit: Mapped[PriceUnitChoices] = mapped_column(Enum(PriceUnitChoices), default=PriceUnitChoices.per_person)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    duration_hours: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[str | None] = mapped_column(String(100))
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    max_altitude: Mapped[int | None] = mapped_column(Integer)
    min_people: Mapped[int] = mapped_column(Integer, default=1)
    max_people: Mapped[int | None] = mapped_column(Integer)
    main_image: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    images: Mapped[list["TrekkingImage"]] = relationship(back_populates="trekking", cascade="all, delete-orphan")
    programs: Mapped[list["TrekkingProgram"]] = relationship(back_populates="trekking", cascade="all, delete-orphan")


class TrekkingImage(Base):
    __tablename__ = "trekking_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trekking_id: Mapped[int] = mapped_column(ForeignKey("trekkings.id", ondelete="CASCADE"), nullable=False)
    image: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    trekking: Mapped["Trekking"] = relationship(back_populates="images")


class TrekkingProgram(LocalizedContent, Base):
    __tablename__ = "trekking_programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trekking_id: Mapped[int] = mapped_column(ForeignKey("trekkings.id", ondelete="CASCADE"), nullable=False)
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str | None] = mapped_column(String(10))
    end_time: Mapped[str | None] = mapped_column(String(10))
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    trekking: Mapped["Trekking"] = relationship(back_populates="programs")

class Contact(LocalizedContent, Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str | None] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(50))
    whatsapp: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    instagram: Mapped[str | None] = mapped_column(String(500))
    facebook: Mapped[str | None] = mapped_column(String(500))
    telegram: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(String(500))
    qr_code: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FAQ(LocalizedContent, Base):
    __tablename__ = "faqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TravelRequest(Base):
    __tablename__ = "travel_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    travel_date: Mapped[date | None] = mapped_column(Date)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    travelers_count: Mapped[int | None] = mapped_column(Integer)
    destination: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[RequestStatusChoices] = mapped_column(Enum(RequestStatusChoices), default=RequestStatusChoices.new, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

