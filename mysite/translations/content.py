"""Stored catalogue translations; public reads never call the translation service."""

import json
from typing import Annotated

from fastapi import Query
from sqlalchemy import inspect

from mysite.translations.jobs import schedule_translation
from mysite.translations.source import (normalize_text, source_field_hash, source_value_changed,
                                        translation_ready)
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
        if translation_ready(value, source_hashes.get(field), getattr(record, field)):
            if getattr(record, field) in (None, ''):
                continue
            result[field] = value
    return result


def mark_manual_translations(translations, source, existing=None, *, compared_to=None):
    if isinstance(translations, str):
        try:
            translations = json.loads(translations) if translations.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError('Translations must be valid JSON') from exc
    if not isinstance(translations, dict):
        return existing if isinstance(existing, dict) else {}
    result = dict(existing) if isinstance(existing, dict) else {}
    comparison = compared_to if isinstance(compared_to, dict) else result
    for language in ('en', 'de', 'zh'):
        values = translations.get(language)
        if not isinstance(values, dict):
            # Missing languages were not present in the submitted form. Preserve
            # worker updates that arrived after the form was rendered.
            continue
        previous = result.get(language)
        previous = dict(previous) if isinstance(previous, dict) else {}
        baseline = comparison.get(language)
        baseline = baseline if isinstance(baseline, dict) else {}
        hashes = previous.get('_source_hashes')
        hashes = dict(hashes) if isinstance(hashes, dict) else {}
        submitted_hashes = values.get('_source_hashes', {})
        submitted_hashes = submitted_hashes if isinstance(submitted_hashes, dict) else {}
        old_manual = previous.get('_manual_fields', [])
        manual = set(old_manual if isinstance(old_manual, list) else [])
        for field, raw_value in values.items():
            if field not in source or not isinstance(raw_value, str):
                continue
            value = normalize_text(raw_value)
            old_value = normalize_text(baseline.get(field))
            if not value.strip():
                current_value = normalize_text(previous.get(field))
                # A worker may have committed a newer translation after the
                # form's baseline was read. An empty stale form value must not
                # erase that concurrent update.
                if current_value != old_value:
                    continue
                previous.pop(field, None)
                hashes.pop(field, None)
                manual.discard(field)
                continue
            if value != old_value:
                current_hash = source_field_hash(source[field])
                form_hash = submitted_hashes.get(field, hashes.get(field))
                if field in previous and form_hash != current_hash:
                    # The form carries a translation for an older source revision.
                    # Preserve it as stale so the current source remains visible.
                    continue
                previous[field] = value
                hashes[field] = current_hash
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
            continue
        previous = existing.get(language)
        if not isinstance(previous, dict):
            previous = {}
        for field in values:
            if not isinstance(field, str):
                continue
            if field.startswith('_'):
                continue
            value = normalize_text(values.get(field))
            if (isinstance(value, str) and not value.strip() and previous.get(field)) or (
                value != normalize_text(previous.get(field))
            ):
                return True
    return False


def manual_translation_needs_refresh(incoming, existing, latest=None):
    """Detect explicit empty values used to clear translations in SQLAdmin."""
    if isinstance(incoming, str):
        try:
            incoming = json.loads(incoming) if incoming.strip() else {}
        except json.JSONDecodeError:
            return False
    if not isinstance(incoming, dict):
        return False
    existing = existing if isinstance(existing, dict) else {}
    latest = latest if isinstance(latest, dict) else existing
    for language in ('en', 'de', 'zh'):
        values = incoming.get(language)
        previous = existing.get(language)
        current = latest.get(language)
        if not isinstance(values, dict) or not isinstance(previous, dict):
            continue
        current = current if isinstance(current, dict) else {}
        for field, value in values.items():
            if not isinstance(field, str):
                continue
            if field.startswith('_'):
                continue
            baseline_value = normalize_text(previous.get(field))
            current_value = normalize_text(current.get(field))
            if (
                isinstance(value, str)
                and not normalize_text(value).strip()
                and isinstance(baseline_value, str)
                and current_value == baseline_value
            ):
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
