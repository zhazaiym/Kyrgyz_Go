from mysite.database.db import SessionLocal
from mysite.database.models import About
from mysite.translations.content import mark_manual_translations
from mysite.translations.jobs import _translation_is_complete, translate_record
from mysite.translations.source import source_field_hash


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
