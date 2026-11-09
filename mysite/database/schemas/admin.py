from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginSchema(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)
    device_token: str | None = Field(default=None, max_length=256)
    remember_device: bool = False


class AdminOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_active: bool
    role: str
    created_at: datetime


class TokenSchema(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    device_token: str | None = None
    device_id: str | None = None
