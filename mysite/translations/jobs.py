"""Queue catalogue translations after commit, without holding a request DB session."""

import logging
from datetime import timedelta
from queue import Queue
from threading import BoundedSemaphore, Event, Lock, Thread

from sqlalchemy import event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from ML.errors import AIError, classify_error
from mysite.api.observability import record_translation_job, set_translation_queue_depth
from mysite.database.db import Base, SessionLocal
from mysite.database.models import Tour, TourTranslation, TranslationJob
from mysite.database.token_utils import utcnow
from mysite.translations.quota import reserve_translation_call
from mysite.translations.source import (TOUR_TRANSLATION_FIELDS, active_manual_fields,
                                        source_field_hash, source_value_changed, translation_ready)

logger = logging.getLogger(__name__)

capacity = BoundedSemaphore(2)
translation_queue = Queue()

_worker_lock = Lock()
_workers_started = False
_pending_jobs = {}
MAX_TRANSLATION_ATTEMPTS = 3
TRANSIENT_ERRORS = {'ai_unavailable', 'ai_rate_limit', 'ai_timeout', 'busy', 'failed'}
_dispatcher_stop = Event()


def _terminal(job):
    return job.status in {'completed', 'obsolete'} or (
        job.status == 'failed' and job.last_error not in TRANSIENT_ERRORS
    )


def schedule_translation(record, fields, translator):
    session = object_session(record)
    if session is None:
        return False

    source = {field: getattr(record, field) for field in fields}

    session.info.setdefault('catalogue_translation_jobs', {})[(type(record), id(record))] = (
        record,
        source,
        translator,
    )

    return True


@event.listens_for(Session, 'after_commit')
def committed(session):
    if not session.in_nested_transaction():
        session.info.setdefault('catalogue_translation_ready', {}).update(
            session.info.pop('catalogue_translation_jobs', {})
        )


@event.listens_for(Session, 'after_rollback')
def rolled_back(session):
    session.info.pop('catalogue_translation_jobs', None)


def committed_jobs(session):
    jobs = session.info.pop('catalogue_translation_ready', {}).values()

    return [
        (type(record), inspect(record).identity[0], source, translator)
        for record, source, translator in jobs
        if inspect(record).identity
    ]


def persist_translation_job(entity, identity, source):
    # Retry only the concurrent first INSERT. Existing pending/running state
    # remains intact, including attempts and the provider's retry deadline.
    for collision in range(2):
        with SessionLocal() as db:
            job = (
                db.query(TranslationJob)
                .filter_by(entity=entity.__tablename__, record_id=identity)
                .with_for_update()
                .first()
            )
            if job is None:
                job = TranslationJob(
                    entity=entity.__tablename__,
                    record_id=identity,
                    source=source,
                    next_attempt_at=utcnow(),
                )
                db.add(job)
            elif job.source == source and _terminal(job):
                return False
            elif job.source != source or job.status == 'failed':
                job.source = source
                job.status = 'pending'
                job.attempts = 0
                job.last_error = None
                job.lease_until = None
                job.next_attempt_at = utcnow()
            try:
                db.commit()
            except IntegrityError:
                if collision:
                    raise
                continue
            return True
    return False


def enqueue_translation(entity, identity, source, translator):
    global _workers_started
    if not persist_translation_job(entity, identity, source):
        return False
    with _worker_lock:
        if not _workers_started:
            _dispatcher_stop.clear()
            Thread(
                target=_dispatch_due_translations,
                name='catalogue-translation-dispatch',
                daemon=True,
            ).start()
            for index in range(2):
                Thread(
                    target=_translation_worker,
                    name=f'catalogue-translation-{index + 1}',
                    daemon=True,
                ).start()

            _workers_started = True

        key = (entity, identity)

        if key in _pending_jobs:
            _pending_jobs[key] = (source, translator)
            return True

        _pending_jobs[key] = (source, translator)
        translation_queue.put_nowait(key)
        set_translation_queue_depth(translation_queue.qsize())
    return True


def _translation_worker():
    while True:
        job = translation_queue.get()

        try:
            with _worker_lock:
                pending = _pending_jobs.pop(job, None)

            if pending is not None:
                source, translator = pending
                result, retry_delay = _run_persisted_translation(job, source, translator)
                record_translation_job(result)
        except Exception:
            logger.error('Translation worker unavailable; durable job will be recovered')
        finally:
            translation_queue.task_done()
            set_translation_queue_depth(translation_queue.qsize())


def _dispatch_due_translations():
    """Retry delays never occupy translation workers."""
    from mysite.translations.content import generate_translations

    entities = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}
    while not _dispatcher_stop.wait(1):
        try:
            now = utcnow()
            with SessionLocal() as db:
                rows = (
                    db.query(TranslationJob)
                    .filter(
                        TranslationJob.status.in_(('pending', 'running')),
                        TranslationJob.next_attempt_at <= now,
                        (TranslationJob.lease_until.is_(None))
                        | (TranslationJob.lease_until <= now),
                    )
                    .order_by(TranslationJob.next_attempt_at, TranslationJob.id)
                    .limit(100)
                    .all()
                )
                due = [(entities.get(row.entity), row.record_id, dict(row.source)) for row in rows]
            for entity, identity, source in due:
                if entity is not None:
                    enqueue_translation(
                        entity,
                        identity,
                        source,
                        _translate_tour if entity is Tour else generate_translations,
                    )
        except Exception:
            logger.error('Translation dispatch unavailable; retrying from durable queue')


def _run_persisted_translation(job, source, translator):
    entity_name, identity = job[0].__tablename__, job[1]
    claimed_lease = None
    try:
        with SessionLocal() as db:
            row = (
                db.query(TranslationJob)
                .filter_by(entity=entity_name, record_id=identity)
                .with_for_update()
                .first()
            )
            if row is None or row.status in {'completed', 'obsolete', 'failed'}:
                return 'missing', 0
            now = utcnow()
            if row.next_attempt_at > now:
                return 'busy', max(1, (row.next_attempt_at - now).total_seconds())
            if row.lease_until is not None and row.lease_until > now:
                return 'busy', max(1, (row.lease_until - now).total_seconds())
            source = dict(row.source)
            row.status = 'running'
            row.attempts += 1
            attempts = row.attempts
            row.lease_until = now + timedelta(minutes=2)
            claimed_lease = row.lease_until
            db.commit()
        result = translate_record(job[0], identity, source, translator, wait_for_capacity=True)
        if result == 'translated' and not _stored_translation_is_complete(job[0], identity, source):
            result = 'invalid_translation'
    except Exception as exc:
        result = exc.code if isinstance(exc, AIError) else 'ai_unavailable'
        logger.error('Translation worker failed code=%s', result)
        attempts = 1

    retry_delay = 0
    with SessionLocal() as db:
        row = (
            db.query(TranslationJob)
            .filter_by(entity=entity_name, record_id=identity)
            .with_for_update()
            .first()
        )
        if (
            row is not None
            and claimed_lease is not None
            and row.source == source
            and row.status == 'running'
            and row.lease_until == claimed_lease
        ):
            row.lease_until = None
            if result in {'translated', 'source_changed', 'missing'}:
                row.status = 'completed' if result == 'translated' else 'obsolete'
                row.last_error = None
            elif result in TRANSIENT_ERRORS or attempts < MAX_TRANSLATION_ATTEMPTS:
                row.status = 'pending'
                row.last_error = result
                retry_delay = min(3600, 2 ** min(attempts, 12))
                row.next_attempt_at = utcnow() + timedelta(seconds=retry_delay)
            else:
                row.status = 'failed'
                row.last_error = result
        db.commit()
    return result, retry_delay


def _stored_translation_is_complete(entity, identity, source):
    with SessionLocal() as db:
        record = db.get(entity, identity)
        if record is None:
            return False
        if entity is Tour:
            rows = db.query(TourTranslation).filter_by(tour_id=identity).all()
            translations = {
                row.lang: {
                    **{field: getattr(row, field) for field in TOUR_TRANSLATION_FIELDS},
                    '_source_hashes': row.source_hashes or {},
                    '_manual_fields': row.manual_fields or [],
                }
                for row in rows
            }
        else:
            translations = record.translations
        return _translation_is_complete(translations, source)


def _translation_is_complete(translations, source):
    if not any(value not in (None, '') for value in source.values()):
        return True

    for language in ('en', 'de', 'zh'):
        values = translations.get(language) if isinstance(translations, dict) else None

        if not isinstance(values, dict):
            return False

        hashes = values.get('_source_hashes', {})
        if not isinstance(hashes, dict):
            return False

        for field, original in source.items():
            if original in (None, ''):
                continue

            if not translation_ready(values.get(field), hashes.get(field), original):
                return False

    return True


def _valid_translation_result(translated, source):
    if not isinstance(translated, dict):
        return {}

    allowed_fields = set(source)
    clean = {}

    for language in ('en', 'de', 'zh'):
        values = translated.get(language)
        if not isinstance(values, dict):
            continue

        fields = {
            field: value
            for field, value in values.items()
            if field in allowed_fields and isinstance(value, str)
        }

        if fields:
            clean[language] = fields

    return clean


def recover_missing_translations(batch_size=100):
    """Requeue missing translations after restarts."""
    from mysite.translations.content import CONTENT_FIELDS, generate_translations

    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')

    entities = {
        mapper.class_.__tablename__: mapper.class_
        for mapper in Base.registry.mappers
        if hasattr(mapper.class_, '__tablename__')
    }

    queued = 0

    for table_name, fields in CONTENT_FIELDS.items():
        entity = entities.get(table_name)

        if entity is None or entity is Tour:
            continue

        last_id = 0

        while True:
            with SessionLocal() as db:
                records = (
                    db.query(entity)
                    .filter(entity.id > last_id)
                    .order_by(entity.id)
                    .limit(batch_size)
                    .all()
                )

                batch = [
                    (
                        record.id,
                        {field: getattr(record, field) for field in fields},
                        record.translations,
                    )
                    for record in records
                ]

            if not batch:
                break

            for identity, source, translations in batch:
                if not _translation_is_complete(translations, source):
                    queued += enqueue_translation(entity, identity, source, generate_translations)

            last_id = batch[-1][0]

    last_id = 0

    while True:
        with SessionLocal() as db:
            tours = (
                db.query(Tour).filter(Tour.id > last_id).order_by(Tour.id).limit(batch_size).all()
            )

            identities = [tour.id for tour in tours]

            sources = {
                tour.id: {field: getattr(tour, field) for field in TOUR_TRANSLATION_FIELDS}
                for tour in tours
            }

            rows = (
                db.query(TourTranslation).filter(TourTranslation.tour_id.in_(identities)).all()
                if identities
                else []
            )

            translated = {}

            for row in rows:
                translated.setdefault(row.tour_id, {})[row.lang] = {
                    **{field: getattr(row, field) for field in TOUR_TRANSLATION_FIELDS},
                    '_source_hashes': row.source_hashes or {},
                    '_manual_fields': row.manual_fields or [],
                }

        if not identities:
            break

        for identity, source in sources.items():
            if not _translation_is_complete(translated.get(identity, {}), source):
                queued += enqueue_translation(Tour, identity, source, _translate_tour)

        last_id = identities[-1]

    return queued


def _translate_tour(source):
    from mysite.translations.translator import translate_tour

    return translate_tour(source)


def translate_record(entity, identity, source, translator, *, wait_for_capacity=False):
    if not capacity.acquire(blocking=wait_for_capacity):
        logger.warning('Catalogue translation capacity exhausted; keeping stored translations')
        return 'busy'

    try:
        # Check the source before calling the translation provider.
        with SessionLocal() as db:
            record = db.get(entity, identity)

            if record is None:
                return 'missing'

            if any(
                source_value_changed(getattr(record, key), value) for key, value in source.items()
            ):
                return 'source_changed'

        reserve_translation_call()
        translated = _valid_translation_result(translator(source), source)

        if not translated:
            return 'invalid_translation'

        with SessionLocal() as db:
            record = db.get(entity, identity, with_for_update=True)

            if record is None:
                return 'missing'

            # The source may have changed while the provider was working.
            if any(
                source_value_changed(getattr(record, key), value) for key, value in source.items()
            ):
                return 'source_changed'

            if entity is Tour:
                for language, values in translated.items():
                    row = (
                        db.query(TourTranslation).filter_by(tour_id=identity, lang=language).first()
                    )

                    if row is None:
                        row = TourTranslation(tour_id=identity, lang=language)
                        db.add(row)

                    hashes = dict(row.source_hashes) if isinstance(row.source_hashes, dict) else {}

                    manual_fields = set(
                        active_manual_fields(row.manual_fields or [], hashes, source)
                    )

                    for field, value in values.items():
                        existing = getattr(row, field)

                        if field in manual_fields and translation_ready(
                            existing, hashes.get(field), source[field]
                        ):
                            continue

                        manual_fields.discard(field)
                        setattr(row, field, value)
                        hashes[field] = source_field_hash(source[field])

                    row.manual_fields = sorted(manual_fields)
                    row.source_hashes = hashes

            else:
                stored = dict(record.translations) if isinstance(record.translations, dict) else {}

                for language, values in translated.items():
                    previous = stored.get(language)
                    previous = dict(previous) if isinstance(previous, dict) else {}

                    hashes = previous.get('_source_hashes', {})
                    hashes = dict(hashes) if isinstance(hashes, dict) else {}

                    manual_fields = set(
                        active_manual_fields(previous.get('_manual_fields', []), hashes, source)
                    )

                    for field, value in values.items():
                        if field in manual_fields and translation_ready(
                            previous.get(field), hashes.get(field), source[field]
                        ):
                            continue

                        manual_fields.discard(field)
                        previous[field] = value
                        hashes[field] = source_field_hash(source[field])

                    previous['_source_hashes'] = hashes
                    previous['_manual_fields'] = sorted(manual_fields)
                    stored[language] = previous

                record.translations = stored

            db.commit()

        return 'translated'

    except Exception as exc:
        # Provider exception messages may contain sensitive information.
        code = (
            exc.code
            if isinstance(exc, AIError)
            else (
                'invalid_translation'
                if isinstance(exc, (ValueError, TypeError))
                else classify_error(exc).code
            )
        )
        if code == 'internal_error':
            code = 'ai_unavailable'
        log = logger.warning if code in TRANSIENT_ERRORS else logger.error
        log('Catalogue translation failed code=%s; source record is already saved', code)
        return code

    finally:
        capacity.release()
