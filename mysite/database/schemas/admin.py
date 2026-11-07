from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminLoginSchema(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(default='', max_length=32)


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
