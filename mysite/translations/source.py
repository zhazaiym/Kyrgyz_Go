"""Shared source identity for stored catalogue translations."""

import hashlib

TOUR_TRANSLATION_FIELDS = ('title', 'description', 'included', 'excluded')


def normalize_text(value):
    """Normalize line endings before comparing or storing text."""
    if isinstance(value, str):
        return value.replace('\r\n', '\n').replace('\r', '\n')
    return value


def _source_value(value):
    """Treat None and an empty string as the same source value."""
    return normalize_text('' if value is None else value)


def source_field_hash(value):
    normalized = str(_source_value(value))

    return hashlib.md5(normalized.encode('utf-8'), usedforsecurity=False).hexdigest()


def source_value_changed(old, new):
    return _source_value(old) != _source_value(new)


def translation_ready(value, stored_hash, source):
    """An empty source needs no translation; other values must match its hash."""
    return source in (None, '') or (
        isinstance(value, str) and bool(value.strip()) and stored_hash == source_field_hash(source)
    )


def active_manual_fields(fields, hashes, source):
    """Keep manual fields whose hashes match the current source."""
    if not isinstance(fields, (list, tuple, set)):
        return []

    if not isinstance(hashes, dict):
        return []

    if not isinstance(source, dict):
        return []

    return sorted(
        {
            field
            for field in fields
            if isinstance(field, str)
            and field in source
            and hashes.get(field) == source_field_hash(source[field])
        }
    )
