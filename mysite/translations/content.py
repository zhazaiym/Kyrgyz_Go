"""Stored catalogue translations; public reads never call the translation service."""

import json

from typing import Annotated

from fastapi import Query
from sqlalchemy import inspect

from mysite.translations.jobs import schedule_translation
from mysite.translations.source import source_field_hash, source_value_changed
from mysite.translations.translator import translate_fields

Language = Annotated[str, Query(pattern='^(ru|en|de|zh)$')]

CONTENT_FIELDS = {
    'abouts': ('title', 'description'),
    'about_sections': ('title', 'description'),
    'tour_categories': ('name',),
    'countries': ('name',),
    'regions': ('name',),
    'districts': ('name',),
    'hotels': ('name', 'description', 'address'),
    'transports': ('name', 'description', 'color'),
    'helicopter_tours': (
        'title',
        'description',
        'destination',
        'departure_location',
        'instruction',
        'included',
    ),
    'trekkings': ('title', 'description', 'route', 'included', 'requirements', 'difficulty'),
    'faqs': ('question', 'answer'),
    'contacts': ('country', 'city', 'address'),
    'tour_programs': ('title', 'description'),
    'trekking_programs': ('title', 'description'),
}


def generate_translations(source):
    """Keep the provider call behind one injectable function for workers and tests."""
    return translate_fields(source)


def localized(record, lang='ru'):
    result = {
        column.key: getattr(record, column.key)
        for column in record.__table__.columns
        if column.key != 'translations'
    }
    translations = record.translations if isinstance(record.translations, dict) else {}
    translation = translations.get(lang, {}) if lang != 'ru' else {}
    if not isinstance(translation, dict):
        translation = {}
    source_hashes = translation.get('_source_hashes', {})
    if not isinstance(source_hashes, dict):
        source_hashes = {}
    for field in CONTENT_FIELDS[record.__tablename__]:
        value = translation.get(field)
        if (
            isinstance(value, str)
            and value
            and source_hashes.get(field) == source_field_hash(getattr(record, field))
        ):
            result[field] = value
    return result


def mark_manual_translations(translations, source, existing=None):
    if isinstance(translations, str):
        try:
            translations = json.loads(translations) if translations.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError('Translations must be valid JSON') from exc
    if not isinstance(translations, dict):
        return existing if isinstance(existing, dict) else {}
    result = dict(existing) if isinstance(existing, dict) else {}
    for language in ('en', 'de', 'zh'):
        values = translations.get(language)
        if not isinstance(values, dict):
            continue
        previous = result.get(language)
        previous = dict(previous) if isinstance(previous, dict) else {}
        hashes = previous.get('_source_hashes')
        hashes = dict(hashes) if isinstance(hashes, dict) else {}
        old_manual = previous.get('_manual_fields', [])
        manual = set(old_manual if isinstance(old_manual, list) else [])
        for field, value in values.items():
            if field not in source or not isinstance(value, str):
                continue
            previous[field] = value
            hashes[field] = source_field_hash(source[field])
            manual.add(field)
        previous['_source_hashes'] = hashes
        previous['_manual_fields'] = sorted(manual)
        result[language] = previous
    return result


def manual_translation_changed(incoming, existing):
    if isinstance(incoming, str):
        try:
            incoming = json.loads(incoming) if incoming.strip() else {}
        except json.JSONDecodeError:
            return True
    if not isinstance(incoming, dict):
        return bool(incoming)
    existing = existing if isinstance(existing, dict) else {}
    for language in ('en', 'de', 'zh'):
        values = incoming.get(language)
        if not isinstance(values, dict):
            values = {}
        previous = existing.get(language)
        if not isinstance(previous, dict):
            previous = {}
        fields = {key for key in values if isinstance(key, str)}
        fields.update(key for key in previous if isinstance(key, str) and not key.startswith('_'))
        for field in fields:
            if field.startswith('_'):
                continue
            if values.get(field) != previous.get(field):
                return True
    return False


def update_translations(record):
    fields = CONTENT_FIELDS[record.__tablename__]
    state = inspect(record)
    changed = state.pending or any(
        state.attrs[field].history.has_changes()
        and source_value_changed(
            state.attrs[field].history.deleted[0] if state.attrs[field].history.deleted else None,
            getattr(record, field),
        )
        for field in fields
    )
    if changed:
        schedule_translation(record, fields, generate_translations)
