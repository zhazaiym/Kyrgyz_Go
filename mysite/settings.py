"""Settings from the environment: each parsed one way and all checked when the app starts.

Groups with their own tables check themselves at start as well: resource limits
(``mysite.api.resource_limits``), chat (``ML.config``), trusted origins
(``mysite.api.origin_config``) and metrics (``mysite.api.observability``).
"""

import os
import re

FLAGS = {
    'API_DOCS': True,
    'SERVE_MEDIA_LOCALLY': True,
    'RATE_LIMIT_ENABLED': True,
    'ADMIN_COOKIE_SECURE': True,
}
NUMBERS = {
    'ADMIN_SESSION_HOURS': (168, 1, 10_000),
    'GEMINI_REQUESTS_PER_MINUTE': (10, 1, 10_000),
    'TRIP_OPTION_RADIUS_KM': (100.0, 1, 2000),
}


def flag(name):
    raw = os.getenv(name, '').strip().casefold()
    if not raw:
        return FLAGS[name]
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    raise RuntimeError(f'{name} must be true or false')


def parse_number(name, default, low, high):
    raw = os.getenv(name, '').strip()
    try:
        value = type(default)(raw) if raw else default
    except ValueError:
        raise RuntimeError(f'{name} must be a number') from None
    if not low <= value <= high:
        raise RuntimeError(f'{name} must be between {low} and {high}')
    return value


def number(name):
    return parse_number(name, *NUMBERS[name])


def admin_domain():
    """The host of the admin panel, such as admin.example.kg, or None when it shares the API host."""
    raw = os.getenv('ADMIN_DOMAIN', '').strip().casefold()
    if not raw:
        return None
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', raw):
        raise RuntimeError('ADMIN_DOMAIN must be a host name such as admin.example.kg')
    return raw


def validate_settings():
    admin_domain()
    for name in FLAGS:
        flag(name)
    for name in NUMBERS:
        number(name)
