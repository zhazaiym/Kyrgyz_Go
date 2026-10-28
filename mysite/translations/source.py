"""Shared source identity for stored catalogue translations."""

import hashlib

TOUR_TRANSLATION_FIELDS = ('title', 'description', 'included', 'excluded')


def normalize_text(value):
    if not isinstance(value, str):
        return value
    return value.replace('\r\n', '\n').replace('\r', '\n')


def source_field_hash(value):
    normalized = '' if value is None or value == '' else normalize_text(value)
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


def source_value_changed(old, new):
    old = '' if old is None or old == '' else old
    new = '' if new is None or new == '' else new
    return normalize_text(old) != normalize_text(new)


def translation_is_ready(value, source, source_hash):
    return (
        isinstance(value, str) and bool(value.strip()) and source_hash == source_field_hash(source)
    )


def active_manual_fields(fields, hashes, source):
    return sorted(
        field
        for field in fields
        if field in source and hashes.get(field) == source_field_hash(source[field])
    )


def attach_source_hashes(translations, source):
    if not isinstance(translations, dict):
        return {}
    result = dict(translations)
    for language in ('en', 'de', 'zh'):
        values = result.get(language)
        if not isinstance(values, dict):
            continue
        values = dict(values)
        hashes = values.get('_source_hashes', {})
        hashes = dict(hashes) if isinstance(hashes, dict) else {}
        for field, translated in values.items():
            if field in source and isinstance(translated, str) and translated.strip():
                hashes[field] = source_field_hash(source[field])
        values['_source_hashes'] = hashes
        result[language] = values
    return result
