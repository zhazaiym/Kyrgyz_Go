import re


def normalize_phone(value: str) -> str:
    normalized = re.sub(r'[\s()\-]', '', value.strip())

    if not re.fullmatch(r'\+?[0-9]{7,15}', normalized):
        raise ValueError('Введите корректный номер телефона')

    return normalized
