"""Validated bounds shared by consultation and provider construction."""

import os

# name: (default, minimum, maximum)
CHAT_SETTINGS = {
    'CHAT_RESPONSE_TIMEOUT': (150, 10, 170),
    'CHAT_HISTORY_MESSAGES': (12, 1, 100),
    'CHAT_HISTORY_CHARACTERS': (8000, 1, 100_000),
    'CHAT_MAX_OUTPUT_TOKENS': (1536, 256, 4096),
    'CHAT_EXTRACT_MAX_OUTPUT_TOKENS': (512, 256, 1024),
}


def integer_setting(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value


def chat_setting(name):
    return integer_setting(name, *CHAT_SETTINGS[name])


def validate_chat_settings():
    """Called at startup, so a typo stops the launch instead of the first chat message."""
    for name in CHAT_SETTINGS:
        chat_setting(name)
