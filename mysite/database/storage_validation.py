"""Storage/domain validation shared by Pydantic and SQLAdmin ORM writes."""

from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from sqlalchemy import Integer, Numeric, String

from mysite.database.booking_validation import optional_email


def validate_storage_values(entity, values, supplied):
    values = dict(values)
    for name, value in values.items():
        if name not in entity.__table__.c:
            continue
        column = entity.__table__.c[name]
        if value is None:
            if name in supplied and not column.nullable:
                raise ValueError(f'{name} cannot be null')
            continue
        if isinstance(column.type, Integer):
            try:
                integer = int(value)
                if Decimal(str(value)) != integer:
                    raise ValueError(f'{name} must be an integer')
                value = values[name] = integer
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise ValueError(f'{name} must be an integer') from exc
        if isinstance(column.type, String) and isinstance(value, str):
            if column.type.length and len(value) > column.type.length:
                raise ValueError(f'{name} exceeds {column.type.length} characters')
            if not column.nullable and not value.strip():
                raise ValueError(f'{name} cannot be blank')
        if isinstance(column.type, Integer) and not -2_147_483_648 <= value <= 2_147_483_647:
            raise ValueError(f'{name} exceeds the integer storage range')
        if isinstance(column.type, Numeric):
            number = Decimal(str(value))
            value = values[name] = number
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
        if name == 'latitude' and not -90 <= value <= 90:
            raise ValueError('latitude must be between -90 and 90')
        if name == 'longitude' and not -180 <= value <= 180:
            raise ValueError('longitude must be between -180 and 180')
        if name == 'email':
            values[name] = optional_email(value)
        if name in {'image', 'main_image', 'qr_code'} and urlsplit(value).scheme.lower() not in {
            '',
            'http',
            'https',
        }:
            raise ValueError(f'Unsafe URL scheme in {name}')
    minimum, maximum = values.get('min_people'), values.get('max_people')
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError('min_people cannot exceed max_people')
    return values
