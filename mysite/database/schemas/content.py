from pydantic import BaseModel, ConfigDict, field_validator

from mysite.database.contact_validation import validate_whatsapp_link
from mysite.database.input_validation import StorageInput


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
