"""Stored catalogue translations; public reads never call the translation service."""

from typing import Annotated

from fastapi import Query
from sqlalchemy import inspect

from mysite.translations.jobs import schedule_translation
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
    for field in CONTENT_FIELDS[record.__tablename__]:
        value = translation.get(field)
        if isinstance(value, str) and value:
            result[field] = value
    return result


def generate_translations(source):
    return translate_fields(source)


def update_translations(record):
    fields = CONTENT_FIELDS[record.__tablename__]
    state = inspect(record)
    if state.pending or any(state.attrs[field].history.has_changes() for field in fields):
        schedule_translation(record, fields, generate_translations)
