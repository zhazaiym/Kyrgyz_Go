"""Validated bounds shared by consultation and provider construction."""

import os


def integer_setting(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f'{name} must be an integer') from exc
    if not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return value


def output_budget(name, default, maximum):
    return max(256, min(maximum, int(os.getenv(name, str(default)))))
