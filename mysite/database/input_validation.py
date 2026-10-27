"""Keep write DTO bounds aligned with their mapped storage columns."""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from pydantic import BaseModel, model_validator
from sqlalchemy import Integer, Numeric, String

from mysite.database import models
from mysite.database.booking_validation import optional_email


class StorageInput(BaseModel):
    @model_validator(mode='after')
    def validate_storage_and_domain(self):
        entity_name = type(self).__name__.removesuffix('InputSchema').removesuffix('UpdateSchema')
        entity = getattr(models, entity_name, None)
        if entity is None:
            return self
        for name in type(self).model_fields:
            if name not in entity.__table__.c:
                continue
            column = entity.__table__.c[name]
            value = getattr(self, name)
            if value is None:
                if name in self.model_fields_set and not column.nullable:
                    raise ValueError(f'{name} cannot be null')
                continue
            if isinstance(column.type, String) and isinstance(value, str):
                if column.type.length and len(value) > column.type.length:
                    raise ValueError(f'{name} exceeds {column.type.length} characters')
                if not column.nullable and not value.strip():
                    raise ValueError(f'{name} cannot be blank')
            if isinstance(column.type, Integer) and not -2_147_483_648 <= value <= 2_147_483_647:
                raise ValueError(f'{name} exceeds the integer storage range')
            if isinstance(column.type, Numeric):
                number = Decimal(value)
                if not number.is_finite() or abs(number) >= 10 ** (
                    column.type.precision - column.type.scale
                ):
                    raise ValueError(f'{name} exceeds the decimal storage range')
                try:
                    if number != number.quantize(Decimal(1).scaleb(-column.type.scale)):
                        raise ValueError(f'{name} has too many decimal places')
                except InvalidOperation as exc:
                    raise ValueError(f'Invalid {name}') from exc
            if (
                name.endswith('_id')
                or name
                in {
                    'day_number',
                    'duration_days',
                    'duration_minutes',
                    'min_people',
                    'max_people',
                    'travelers_count',
                    'seats',
                    'max_passengers',
                }
            ) and value < 1:
                raise ValueError(f'{name} must be positive')
            if (
                name in {'price', 'duration_nights', 'duration_hours', 'distance_km', 'order'}
                and value < 0
            ):
                raise ValueError(f'{name} cannot be negative')
            if name == 'stars' and not 1 <= value <= 5:
                raise ValueError('stars must be between 1 and 5')
            if name == 'email':
                setattr(self, name, optional_email(value))
            if name in {'image', 'main_image', 'qr_code'} and urlsplit(
                value
            ).scheme.lower() not in {'', 'http', 'https'}:
                raise ValueError(f'Unsafe URL scheme in {name}')
        minimum, maximum = (getattr(self, 'min_people', None), getattr(self, 'max_people', None))
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError('min_people cannot exceed max_people')
        return self
