import asyncio
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from mysite.admin.views import LocalizedAdminMixin
from mysite.api.tour import get_localized_tour
from mysite.database.db import SessionLocal
from mysite.database.models import About, Tour
from mysite.translations.content import (localized, manual_translation_changed,
                                         manual_translation_needs_refresh, mark_manual_translations)
from mysite.translations.jobs import _translation_is_complete, translate_record
from mysite.translations.source import source_field_hash, translation_ready


def test_translation_migration_downgrade_removes_stale_values(monkeypatch):
    from tests.postgres_support import temporary_database

    with temporary_database() as url:
        script = """
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
import hashlib
from mysite.translations.source import source_field_hash, translation_ready

config = Config('alembic.ini')
command.upgrade(config, '20261028_0013')
engine = create_engine(__import__('os').environ['DATABASE_URL'])
try:
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO abouts (title, description, experience_years, travelers_count, "
            "branches_count, destinations_count, routes_count, is_active, translations) "
            "VALUES (E'Old\\r\\nsource', 'Description', 1, 1, 1, 1, 1, true, "
            "CAST(:translations AS json))"
        ), {'translations': '{"en":{"title":"Old translation"}}'})
        connection.execute(text(
            "INSERT INTO tours (title, price, price_unit, min_people, tour_type, "
            "is_active, created_at, updated_at) VALUES "
            "('Old tour', 1, 'per_person', 1, 'classic', true, now(), now())"
        ))
        connection.execute(text(
            "INSERT INTO tours (title, description, price, price_unit, min_people, tour_type, "
            "is_active, created_at, updated_at) VALUES "
            "(:title, :description, 1, 'per_person', 1, 'classic', true, now(), now())"
        ), {'title': 'CRLF\\r\\nTour', 'description': 'First\\r\\nSecond'})
        connection.execute(text(
            "INSERT INTO tours (title, description, price, price_unit, min_people, tour_type, "
            "is_active, created_at, updated_at) VALUES "
            "(:title, :description, 1, 'per_person', 1, 'classic', true, now(), now())"
        ), {'title': 'No translation\\r\\nTour', 'description': 'Still\\r\\nnormalized'})
        connection.execute(text(
            "INSERT INTO tour_translations (tour_id, lang, title) "
            "VALUES (1, 'en', 'Old tour translation')"
        ))
        connection.execute(text(
            "INSERT INTO tour_translations (tour_id, lang, title, description) "
            "VALUES (2, 'en', 'English title', 'English description')"
        ))
    command.upgrade(config, 'head')
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO rate_limit_counters (key_hash, window_start, request_count) "
            "VALUES ('legacy-insert', 1, 1)"
        ))
        assert connection.scalar(text(
            "SELECT scope FROM rate_limit_counters WHERE key_hash='legacy-insert'"
        )) == ''
        translated = connection.scalar(text("SELECT translations FROM abouts WHERE id=1"))
        expected = hashlib.md5('Old\\nsource'.encode(), usedforsecurity=False).hexdigest()
        assert translated['en']['_source_hashes']['title'] == expected
        assert connection.scalar(text("SELECT title FROM abouts WHERE id=1")) == 'Old\\nsource'
        tour = connection.execute(
            text("SELECT title, description FROM tours WHERE id=2")
        ).mappings().one()
        tour_translation = connection.execute(
            text("SELECT title, description, source_hashes FROM tour_translations WHERE tour_id=2")
        ).mappings().one()
        assert tour['title'] == 'CRLF\\nTour'
        assert tour['description'] == 'First\\nSecond'
        assert tour_translation['source_hashes']['title'] == source_field_hash('CRLF\\nTour')
        assert tour_translation['source_hashes']['description'] == source_field_hash('First\\nSecond')
        assert translation_ready(
            tour_translation['title'],
            tour_translation['source_hashes']['title'],
            tour['title'],
        )
        assert connection.scalar(text("SELECT title FROM tours WHERE id=3")) == 'No translation\\nTour'
    with engine.begin() as connection:
        connection.execute(text("UPDATE abouts SET title = 'New source' WHERE id = 1"))
        connection.execute(text("UPDATE tours SET title = 'New tour' WHERE id = 1"))
    command.downgrade(config, '20261028_0013')
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT translations FROM abouts WHERE id=1")) is None
        assert connection.scalar(text("SELECT title FROM tour_translations WHERE tour_id=1")) == ''
finally:
    engine.dispose()
"""
        env = {**os.environ, 'DATABASE_URL': url}
        env.pop('GEMINI_API_KEY', None)
        result = subprocess.run(
            [sys.executable, '-B', '-c', script], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr


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


def test_sqladmin_marks_only_changed_translation_field_as_manual():
    old_source = {'title': 'Old title', 'description': 'Old description'}
    source = old_source
    existing = {
        language: {
            'title': f'{old_source["title"]} {language}',
            'description': f'{old_source["description"]} {language}',
            '_source_hashes': {
                field: source_field_hash(value) for field, value in old_source.items()
            },
            '_manual_fields': [],
        }
        for language in ('en', 'de', 'zh')
    }
    incoming = {
        lang: {field: value for field, value in existing[lang].items() if not field.startswith('_')}
        for lang in ('en', 'de', 'zh')
    }
    incoming['en']['title'] = 'Edited English title'

    marked = mark_manual_translations(incoming, source, existing)

    assert marked['en']['_manual_fields'] == ['title']
    assert marked['en']['_source_hashes']['title'] == source_field_hash(source['title'])
    for language in ('en', 'de', 'zh'):
        for field in ('title', 'description'):
            if (language, field) != ('en', 'title'):
                assert marked[language]['_source_hashes'][field] == source_field_hash(
                    old_source[field]
                )
                assert field not in marked[language]['_manual_fields']


def test_unchanged_stale_translation_form_does_not_refresh_its_hash():
    source = {'title': 'Current title'}
    old_hash = source_field_hash('Previous title')
    existing = {'en': {'title': 'Old English title', '_source_hashes': {'title': old_hash}}}

    assert not manual_translation_changed({'en': {'title': 'Old English title'}}, existing)
    saved = mark_manual_translations({'en': {'title': 'Old English title'}}, source, existing)
    assert saved['en']['_source_hashes']['title'] == old_hash
    assert not _translation_is_complete(saved, source)


def test_admin_merge_keeps_translation_written_after_form_was_loaded():
    source = {'title': 'Current title'}
    current_hash = source_field_hash(source['title'])
    form_snapshot = {'en': {'title': 'Previous English', '_source_hashes': {'title': current_hash}}}
    latest = {'en': {'title': 'Worker English', '_source_hashes': {'title': current_hash}}}

    merged = mark_manual_translations(form_snapshot, source, latest, compared_to=form_snapshot)

    assert merged['en']['title'] == 'Worker English'
    assert merged['en']['_manual_fields'] == []


def test_translation_readiness_uses_same_whitespace_and_source_rules():
    assert source_field_hash('line one\r\nline two') == source_field_hash('line one\nline two')
    assert not translation_ready('   ', source_field_hash('source'), 'source')
    assert not translation_ready('translated', source_field_hash('old'), 'source')
    assert translation_ready('translated', source_field_hash('source'), 'source')

    source = {'title': 'Visible source', 'description': 'Description'}
    whitespace = {
        language: {
            'title': '   ',
            'description': 'Translated description',
            '_source_hashes': {field: source_field_hash(value) for field, value in source.items()},
        }
        for language in ('en', 'de', 'zh')
    }
    record = About(**source, translations=whitespace)
    assert localized(record, 'en')['title'] == source['title']
    assert not _translation_is_complete(whitespace, source)


@pytest.mark.parametrize(
    'blank', ['\n\t', '\u00a0', '\u2007', '\u202f', '\u0085', '\u3000', '\u2028', '\x1c']
)
def test_tour_display_and_search_fall_back_for_whitespace_translation(client, blank):
    from mysite.database import models

    marker = 'WhitespaceTourFallback'
    with SessionLocal() as db:
        tour = Tour(title=marker, price=10)
        db.add(tour)
        db.flush()
        db.execute(
            text(
                'INSERT INTO tour_translations (tour_id, lang, title, source_hashes, manual_fields) '
                "VALUES (:tour_id, 'en', :blank, CAST(:hashes AS json), '[]')"
            ),
            {
                'tour_id': tour.id,
                'blank': blank,
                'hashes': '{"title":"' + source_field_hash(marker) + '"}',
            },
        )
        tour_id = tour.id
        db.commit()
        tour = db.get(models.Tour, tour_id)
        assert get_localized_tour(tour, db, 'en')['title'] == marker
        from mysite.api.filter_utils import _display_field

        assert (
            db.scalar(select(_display_field(Tour, 'title', 'en')).where(Tour.id == tour_id))
            == marker
        )

    response = client.get('/tours/', params={'lang': 'en', 'search': marker})
    assert response.status_code == 200, response.text
    assert any(item['id'] == tour_id and item['title'] == marker for item in response.json())


def test_sql_whitespace_matches_python_strip_independent_of_locale():
    from sqlalchemy import literal

    from mysite.api.filter_utils import _has_non_whitespace

    values = [chr(code) for code in range(0x3100) if chr(code).isspace()]
    values += [''.join(values), '', '\u200b', ' \u00a0text\u202f ']
    with SessionLocal() as db:
        for value in values:
            assert db.scalar(select(_has_non_whitespace(literal(value)))) == bool(value.strip())


def test_sqladmin_crlf_is_normalized_before_translation_change_detection():
    existing = {'en': {'description': 'line one\nline two'}}
    assert not manual_translation_changed({'en': {'description': 'line one\r\nline two'}}, existing)


def test_whitespace_manual_translation_is_treated_as_explicit_clear():
    source = {'title': 'Source'}
    existing = {
        'en': {
            'title': 'Existing translation',
            '_source_hashes': {'title': source_field_hash('Source')},
            '_manual_fields': ['title'],
        }
    }
    incoming = {'en': {'title': '\n\t'}}

    assert manual_translation_needs_refresh(incoming, existing)
    cleared = mark_manual_translations(incoming, source, existing, compared_to=existing)
    assert 'title' not in cleared['en']
    assert cleared['en']['_manual_fields'] == []


def test_sqladmin_lf_and_crlf_source_are_equal_and_do_not_schedule_translation():
    record = About(title='Title', description='line one\nline two')
    record.translations = {'en': {'title': 'Title en'}}
    data = {
        'title': 'Title',
        'description': 'line one\r\nline two',
        'translations': record.translations,
    }
    request = SimpleNamespace(state=SimpleNamespace())

    asyncio.run(LocalizedAdminMixin.on_model_change(None, data, record, False, request))

    assert data['description'] == 'line one\nline two'
    assert not hasattr(request.state, 'catalogue_source')


def test_stale_manual_field_falls_back_to_source_then_can_be_regenerated():
    old_source = {'title': 'Old title', 'description': 'Description'}
    with SessionLocal() as db:
        record = About(title=old_source['title'], description=old_source['description'])
        record.translations = mark_manual_translations(
            {'en': {'title': 'Manual old title'}}, old_source
        )
        db.add(record)
        db.commit()
        identity = record.id
        record.title = 'Current title'
        db.commit()

    with SessionLocal() as db:
        record = db.get(About, identity)
        assert localized(record, 'en')['title'] == 'Current title'

    source = {'title': 'Current title', 'description': 'Description'}
    result = translate_record(
        About,
        identity,
        source,
        lambda values: {
            language: {field: f'{value} ({language})' for field, value in values.items()}
            for language in ('en', 'de', 'zh')
        },
    )
    assert result == 'translated'
    with SessionLocal() as db:
        record = db.get(About, identity)
        assert localized(record, 'en')['title'] == 'Current title (en)'
        assert 'title' not in record.translations['en']['_manual_fields']


def test_translation_migrations_preserve_current_normalized_hashes_and_leave_stale_hashes():
    from tests.postgres_support import temporary_database

    script = r"""
import hashlib
import json
import os
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from mysite.translations.source import source_field_hash, translation_ready
config = Config('alembic.ini')
command.upgrade(config, '20261028_0015')
engine = create_engine(os.environ['DATABASE_URL'])
fields = ('title', 'description', 'included', 'excluded')
source = dict(zip(fields, ('Title\r\nTail', 'Description\rTail', 'Included\r\r\nTail', 'Excluded\rTail')))
raw_hash = lambda value: hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()
try:
    with engine.begin() as c:
        identity = c.execute(text(
            'INSERT INTO tours (title, description, included, excluded, price, price_unit, min_people, '
            'tour_type, is_active, created_at, updated_at) VALUES '
            "(:title, :description, :included, :excluded, 1, 'per_person', 1, 'classic', true, now(), now()) RETURNING id"
        ), source).scalar_one()
        stale_hash = raw_hash('Earlier source')
        for lang in ('en', 'de'):
            hashes = {field: raw_hash(value) for field, value in source.items()}
            if lang == 'de':
                hashes['title'] = stale_hash
            c.execute(text(
                'INSERT INTO tour_translations (tour_id, lang, title, description, included, excluded, source_hashes) '
                'VALUES (:id, :lang, :title, :description, :included, :excluded, CAST(:hashes AS json))'
            ), dict(id=identity, lang=lang, hashes=json.dumps(hashes), **{f: f'{lang} {f}' for f in fields}))
    command.upgrade(config, 'head')
    with engine.begin() as c:
        current = c.execute(text('SELECT title, description, included, excluded FROM tours WHERE id=:id'), {'id':identity}).mappings().one()
        for field, value in source.items():
            assert current[field] == value.replace('\r\n','\n').replace('\r','\n')
        rows = c.execute(text('SELECT * FROM tour_translations WHERE tour_id=:id'), {'id':identity}).mappings().all()
        for row in rows:
            for field in fields:
                if row['lang'] == 'de' and field == 'title':
                    assert row['source_hashes'][field] == stale_hash
                    assert not translation_ready(row[field], stale_hash, current[field])
                else:
                    assert row['source_hashes'][field] == source_field_hash(current[field])
                    assert translation_ready(row[field], row['source_hashes'][field], current[field])
        # New application writes CRLF with a normalized hash. Downgrade must
        # retain these current values while still removing the stale German title.
        c.execute(text('UPDATE tours SET title=:title, description=:description, included=:included, excluded=:excluded WHERE id=:id'), dict(source,id=identity))
        for raw in (False, True):
            title = 'About\r\nTitle'
            hashes = {'title': raw_hash(title) if raw else source_field_hash(title)}
            c.execute(text(
                'INSERT INTO abouts (title, experience_years, travelers_count, branches_count, destinations_count, routes_count, is_active, translations) '
                'VALUES (:title,1,1,1,1,1,true,CAST(:translations AS json))'
            ), {'title':title, 'translations':json.dumps({'en':{'title':'Current about', '_source_hashes':hashes}})})
    command.downgrade(config, '20261028_0013')
    with engine.connect() as c:
        rows = c.execute(text('SELECT * FROM tour_translations WHERE tour_id=:id'), {'id':identity}).mappings().all()
        for row in rows:
            for field in fields:
                assert row[field] == ('' if row['lang']=='de' and field=='title' else f"{row['lang']} {field}")
        for translated in c.execute(text('SELECT translations FROM abouts')).scalars():
            assert translated['en']['title'] == 'Current about'
finally:
    engine.dispose()
"""
    with temporary_database() as url:
        env = {**os.environ, 'DATABASE_URL': url}
        env.pop('GEMINI_API_KEY', None)
        result = subprocess.run(
            [sys.executable, '-B', '-c', script], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stdout + result.stderr
