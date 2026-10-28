"""Shared source identity for stored catalogue translations."""

import hashlib

TOUR_TRANSLATION_FIELDS = ('title', 'description', 'included', 'excluded')


def normalize_text(value):
    """Normalize line endings before comparing or storing admin text fields."""
    if isinstance(value, str):
        return value.replace('\r\n', '\n').replace('\r', '\n')
    return value


def _source_value(value):
    return normalize_text('' if value is None else value)


def source_field_hash(value):
    return hashlib.md5(str(_source_value(value)).encode('utf-8'), usedforsecurity=False).hexdigest()


def source_value_changed(old, new):
    return _source_value(old) != _source_value(new)


def translation_ready(value, stored_hash, source):
    """Whether a translated field is safe to display and complete for recovery."""
    if source in (None, ''):
        return True
    return (
        isinstance(value, str) and bool(value.strip()) and stored_hash == source_field_hash(source)
    )
