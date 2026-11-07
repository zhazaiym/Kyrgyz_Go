from concurrent.futures import ThreadPoolExecutor

from mysite.database.db import SessionLocal
from mysite.database.models import About, TranslationJob
from mysite.database.token_utils import utcnow
from mysite.translations.jobs import _run_persisted_translation, persist_translation_job


def test_translation_enqueue_is_idempotent_across_workers(client):
    with SessionLocal() as db:
        record = About(title='Persistent queue probe')
        db.add(record)
        db.commit()
        identity = record.id

    source = {'title': 'Persistent queue probe'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: persist_translation_job(About, identity, source), range(2))
        )

    with SessionLocal() as db:
        jobs = db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity)
        assert jobs.count() == 1
        job = jobs.one()
        assert job.source == source
        assert job.status == 'pending'
        assert job.attempts == 0
    assert results == [True, True]


def test_translation_retry_state_survives_duplicate_startup_recovery(client):
    source = {'title': 'Retry state probe'}
    with SessionLocal() as db:
        record = About(title=source['title'])
        db.add(record)
        db.commit()
        identity = record.id
        db.add(
            TranslationJob(
                entity=About.__tablename__,
                record_id=identity,
                source=source,
                status='pending',
                attempts=3,
                last_error='failed',
            )
        )
        db.commit()

    assert persist_translation_job(About, identity, source)
    with SessionLocal() as db:
        job = (
            db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity).one()
        )
        assert job.attempts == 3
        assert job.last_error == 'failed'

    assert persist_translation_job(About, identity, {'title': 'New source text'})
    with SessionLocal() as db:
        job = (
            db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity).one()
        )
        assert job.source == {'title': 'New source text'}
        assert job.status == 'pending'
        assert job.attempts == 0
        assert job.last_error is None


def test_terminal_translation_failure_stays_capped_for_same_source(client):
    source = {'title': 'Terminal failure probe'}
    with SessionLocal() as db:
        record = About(title=source['title'])
        db.add(record)
        db.commit()
        identity = record.id
        db.add(
            TranslationJob(
                entity=About.__tablename__,
                record_id=identity,
                source=source,
                status='failed',
                attempts=5,
                last_error='failed',
            )
        )
        db.commit()

    assert not persist_translation_job(About, identity, source)


def test_transient_translation_failure_is_scheduled_and_eventually_completes(client):
    source = {'title': 'Transient retry probe'}
    with SessionLocal() as db:
        record = About(title=source['title'])
        db.add(record)
        db.commit()
        identity = record.id
    persist_translation_job(About, identity, source)

    def transient_failure(_source):
        raise TimeoutError('provider details are not persisted')

    result, delay = _run_persisted_translation((About, identity), source, transient_failure)
    assert result == 'failed'
    assert delay == 2
    with SessionLocal() as db:
        job = (
            db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity).one()
        )
        assert job.status == 'pending'
        assert job.attempts == 1
        assert job.last_error == 'failed'
        job.next_attempt_at = utcnow()
        db.commit()

    def successful_translation(values):
        return {language: dict(values) for language in ('en', 'de', 'zh')}

    result, delay = _run_persisted_translation((About, identity), source, successful_translation)
    assert result == 'translated'
    assert delay == 0
    with SessionLocal() as db:
        job = (
            db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity).one()
        )
        assert job.status == 'completed'
        assert job.attempts == 2


def test_stale_worker_does_not_discard_newer_source(client):
    source = {'title': 'Original source'}
    replacement = {'title': 'Edited while translating'}
    with SessionLocal() as db:
        record = About(title=source['title'])
        db.add(record)
        db.commit()
        identity = record.id
    persist_translation_job(About, identity, source)

    def edit_during_translation(values):
        with SessionLocal() as db:
            record = db.get(About, identity)
            record.title = replacement['title']
            db.commit()
        assert persist_translation_job(About, identity, replacement)
        return {language: dict(values) for language in ('en', 'de', 'zh')}

    result, delay = _run_persisted_translation((About, identity), source, edit_during_translation)
    assert result == 'source_changed'
    assert delay == 0
    with SessionLocal() as db:
        job = (
            db.query(TranslationJob).filter_by(entity=About.__tablename__, record_id=identity).one()
        )
        assert job.source == replacement
        assert job.status == 'pending'
        assert job.attempts == 0

    result, delay = _run_persisted_translation(
        (About, identity),
        replacement,
        lambda values: {language: dict(values) for language in ('en', 'de', 'zh')},
    )
    assert result == 'translated'
    assert delay == 0
