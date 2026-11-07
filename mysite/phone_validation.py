import re
from typing import Annotated

from pydantic import AfterValidator


def normalize_phone(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Введите корректный номер телефона')
    normalized = re.sub(r'[\s()\-]', '', value.strip())

    if not re.fullmatch(r'\+?[0-9]{7,15}', normalized):
        raise ValueError('Введите корректный номер телефона')

    return normalized


Phone = Annotated[str, AfterValidator(normalize_phone)]
