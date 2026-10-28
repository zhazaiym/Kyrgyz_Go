"""Queue catalogue translations after commit, without holding a request DB session."""

import logging
from queue import Queue
from threading import BoundedSemaphore, Lock, Thread

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, object_session

from mysite.database.db import Base, SessionLocal
from mysite.database.models import Tour, TourTranslation
from mysite.translations.source import (
    TOUR_TRANSLATION_FIELDS,
    active_manual_fields,
    source_field_hash,
    source_value_changed,
    translation_is_ready,
)

logger = logging.getLogger(__name__)
capacity = BoundedSemaphore(2)
translation_queue = Queue()
_worker_lock = Lock()
_workers_started = False
_pending_jobs = {}


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


def enqueue_translation(entity, identity, source, translator):
    global _workers_started
    with _worker_lock:
        if not _workers_started:
            for index in range(2):
                Thread(
                    target=_translation_worker,
                    name=f'catalogue-translation-{index + 1}',
                    daemon=True,
                ).start()
            _workers_started = True
    key = (entity, identity)
    with _worker_lock:
        if key in _pending_jobs:
            _pending_jobs[key] = (source, translator)
            return True
        _pending_jobs[key] = (source, translator)
        translation_queue.put_nowait(key)
    return True


def _translation_worker():
    while True:
        job = translation_queue.get()
        try:
            with _worker_lock:
                pending = _pending_jobs.pop(job, None)
            if pending is not None:
                source, translator = pending
                translate_record(job[0], job[1], source, translator, wait_for_capacity=True)
        finally:
            translation_queue.task_done()


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
        manual = values.get('_manual_fields', [])
        manual_fields = set(manual if isinstance(manual, list) else [])
        for field, original in source.items():
            if field in manual_fields and hashes.get(field) == source_field_hash(original):
                continue
            translated_value = values.get(field)
            if original not in (None, '') and not translation_is_ready(
                translated_value, original, hashes.get(field)
            ):
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
    """Requeue missing translations after restarts; stale text is never served meanwhile."""
    from mysite.translations.content import CONTENT_FIELDS, generate_translations

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
        if not tours:
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
        # Skip obsolete queued work before paying for an external model call.
        with SessionLocal() as db:
            record = db.get(entity, identity)
            if record is None:
                return 'missing'
            if any(
                source_value_changed(getattr(record, key), value) for key, value in source.items()
            ):
                return 'source_changed'
        translated = _valid_translation_result(translator(source), source)
        if not translated:
            return 'invalid_translation'
        with SessionLocal() as db:
            record = db.get(entity, identity, with_for_update=True)
            if record is None:
                return 'missing'
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
                    hashes = dict(row.source_hashes or {})
                    manual_fields = set(
                        active_manual_fields(row.manual_fields or [], hashes, source)
                    )
                    for field, value in values.items():
                        if field not in manual_fields:
                            setattr(row, field, value)
                            hashes[field] = source_field_hash(source[field])
                    row.source_hashes = hashes
                    row.manual_fields = sorted(manual_fields)
            else:
                stored = dict(record.translations) if isinstance(record.translations, dict) else {}
                for language, values in translated.items():
                    previous = stored.get(language)
                    previous = previous if isinstance(previous, dict) else {}
                    previous = dict(previous)
                    hashes = dict(previous.get('_source_hashes', {}))
                    manual_fields = set(
                        active_manual_fields(previous.get('_manual_fields', []), hashes, source)
                    )
                    for field, value in values.items():
                        if field not in manual_fields:
                            previous[field] = value
                            hashes[field] = source_field_hash(source[field])
                    previous['_source_hashes'] = hashes
                    previous['_manual_fields'] = sorted(manual_fields)
                    stored[language] = previous
                record.translations = stored
            db.commit()
        return 'translated'
    except Exception:
        logger.exception('Catalogue translation failed; source record is already saved')
        return 'failed'
    finally:
        capacity.release()
