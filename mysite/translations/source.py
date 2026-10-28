"""Shared source identity for stored catalogue translations."""

import hashlib

TOUR_TRANSLATION_FIELDS = ('title', 'description', 'included', 'excluded')


def source_field_hash(value):
    normalized = '' if value is None or value == '' else value
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


def source_value_changed(old, new):
    old = '' if old is None or old == '' else old
    new = '' if new is None or new == '' else new
    return old != new
