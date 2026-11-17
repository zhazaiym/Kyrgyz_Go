from pydantic import BaseModel, ConfigDict


class AboutOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    is_active: bool


class AboutSectionOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    description: str | None
    image: str | None
    order: int
    is_active: bool


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


class FAQOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    answer: str
    order: int
    is_active: bool
