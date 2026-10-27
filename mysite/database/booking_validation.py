"""Validation shared by model extraction and the booking write boundary."""

from email_validator import validate_email


def optional_email(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 254:
        raise ValueError('Invalid email')
    if not value.strip():
        return None
    return validate_email(value.strip(), check_deliverability=False).normalized.lower()
