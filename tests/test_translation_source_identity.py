import asyncio
from types import SimpleNamespace

from mysite.database.db import SessionLocal
from mysite.database.models import About
from mysite.translations.content import (
    localized,
    mark_manual_translations,
    manual_translation_changed,
    release_stale_manual_translations,
)
from mysite.translations.jobs import _translation_is_complete, translate_record
from mysite.translations.source import source_field_hash, source_value_changed


def test_translation_recovery_treats_none_as_missing():
    source = {'title': 'A tour', 'description': 'A description'}
    translations = {
        language: {
            'title': 'A tour translated',
            'description': None,
            '_source_hashes': {
                'title': source_field_hash(source['title']),
                'description': source_field_hash(source['description']),
            },
        }
        for language in ('en', 'de', 'zh')
    }

    assert not _translation_is_complete(translations, source)


def test_translation_display_and_recovery_both_reject_whitespace():
    source = {'title': 'A tour'}
    translations = {
        language: {'title': '   ', '_source_hashes': {'title': source_field_hash(source['title'])}}
        for language in ('en', 'de', 'zh')
    }

    assert not _translation_is_complete(translations, source)


def test_translation_comparison_normalizes_crlf():
    assert source_field_hash('line one\r\nline two') == source_field_hash('line one\nline two')
    assert not source_value_changed('line one\r\nline two', 'line one\nline two')


def test_sqladmin_marks_only_changed_translation_fields_and_removes_empty_fields():
    source = {'title': 'Current title', 'description': 'Current description'}
    hashes = {field: source_field_hash(value) for field, value in source.items()}
    existing = {
        'en': {
            'title': 'English title',
            'description': 'English description',
            '_source_hashes': hashes,
            '_manual_fields': [],
        },
        'de': {
            'title': 'Deutscher Titel',
            '_source_hashes': {'title': hashes['title']},
            '_manual_fields': [],
        },
    }
    incoming = {
        'en': {'title': 'Edited English title', 'description': 'English description'},
        'de': {'title': 'Deutscher Titel'},
    }

    assert manual_translation_changed(incoming, existing)
    updated = mark_manual_translations(incoming, source, existing)

    assert updated['en']['_manual_fields'] == ['title']
    assert updated['de']['_manual_fields'] == []
    assert updated['en']['description'] == 'English description'

    incoming['en']['title'] = ''
    updated = mark_manual_translations(incoming, source, updated)
    assert 'title' not in updated['en']
    assert 'title' not in updated['en']['_source_hashes']
    assert 'title' not in updated['en']['_manual_fields']


def test_old_sqladmin_payload_does_not_mark_stale_translation_as_current():
    old_source = {'title': 'Before edit', 'description': None}
    new_source = {'title': 'After edit', 'description': None}
    existing = mark_manual_translations({'en': {'title': 'Translation of old title'}}, old_source)

    assert not manual_translation_changed(existing, existing)
    unchanged = mark_manual_translations(existing, new_source, existing)
    released = release_stale_manual_translations(unchanged, new_source)
    assert released['en']['_source_hashes']['title'] == source_field_hash('Before edit')
    assert released['en']['_manual_fields'] == []


def test_sqladmin_source_edit_does_not_rehash_unchanged_old_translation():
    from mysite.admin.views import AboutAdmin

    old_source = {'title': 'Before edit', 'description': None}
    new_source = {'title': 'After edit', 'description': None}
    existing = mark_manual_translations({'en': {'title': 'Translation of old title'}}, old_source)
    model = About(title=old_source['title'], description=None, translations=existing)
    data = {**new_source, 'translations': existing}
    request = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(AboutAdmin().on_model_change(data, model, False, request))

    assert request.state.catalogue_source == new_source
    assert data['translations']['en']['_source_hashes']['title'] == source_field_hash('Before edit')
    assert data['translations']['en']['_manual_fields'] == []


def test_stale_translation_job_does_not_overwrite_manual_translation():
    source = {'title': 'Old title', 'description': 'Old description'}
    with SessionLocal() as db:
        record = About(title=source['title'], description=source['description'])
        record.translations = mark_manual_translations(
            {'en': {'title': 'Human translation'}}, source
        )
        db.add(record)
        db.commit()
        identity = record.id

    def update_source_during_translation(values):
        with SessionLocal() as db:
            record = db.get(About, identity)
            record.title = 'New title'
            db.commit()
        return {
            language: {'title': 'Machine title', 'description': 'Machine description'}
            for language in ('en', 'de', 'zh')
        }

    assert (
        translate_record(About, identity, source, update_source_during_translation)
        == 'source_changed'
    )

    with SessionLocal() as db:
        record = db.get(About, identity)
        assert record.translations['en']['title'] == 'Human translation'
        assert record.translations['en']['_manual_fields'] == ['title']


def test_localized_content_falls_back_when_source_hash_is_stale():
    source = {'title': 'Current title'}
    record = About(
        title=source['title'],
        translations={
            'en': {
                'title': 'Old translation',
                '_source_hashes': {'title': source_field_hash('Old title')},
            }
        },
    )

    assert localized(record, 'en')['title'] == source['title']
