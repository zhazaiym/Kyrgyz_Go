"""Queue catalogue translations after commit, without holding a request DB session."""

import logging
from queue import Full, Queue
from threading import BoundedSemaphore, Lock, Thread

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, object_session

from mysite.database.db import SessionLocal
from mysite.database.models import Tour, TourTranslation

logger = logging.getLogger(__name__)
capacity = BoundedSemaphore(2)
translation_queue = Queue(maxsize=512)
_worker_lock = Lock()
_workers_started = False


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
    try:
        translation_queue.put((entity, identity, source, translator), timeout=0.1)
        return True
    except Full:
        logger.error('Catalogue translation queue is full; existing translations were retained')
        return False


def _translation_worker():
    while True:
        job = translation_queue.get()
        try:
            translate_record(*job, wait_for_capacity=True)
        finally:
            translation_queue.task_done()


def translate_record(entity, identity, source, translator, *, wait_for_capacity=False):
    if not capacity.acquire(blocking=wait_for_capacity):
        logger.warning('Catalogue translation capacity exhausted; keeping stored translations')
        return 'busy'
    try:
        # No database session is open while the external service is called.
        translated = translator(source)
        with SessionLocal() as db:
            record = db.get(entity, identity, with_for_update=True)
            if record is None:
                return 'missing'
            if any(getattr(record, key) != value for key, value in source.items()):
                return 'source_changed'
            if entity is Tour:
                for language, values in translated.items():
                    row = (
                        db.query(TourTranslation).filter_by(tour_id=identity, lang=language).first()
                    )
                    if row is None:
                        db.add(TourTranslation(tour_id=identity, lang=language, **values))
                    else:
                        for key, value in values.items():
                            setattr(row, key, value)
            else:
                stored = dict(record.translations) if isinstance(record.translations, dict) else {}
                for language, values in translated.items():
                    previous = stored.get(language)
                    previous = previous if isinstance(previous, dict) else {}
                    stored[language] = {**previous, **values}
                record.translations = stored
            db.commit()
        return 'translated'
    except Exception:
        logger.exception('Catalogue translation failed; source record is already saved')
        return 'failed'
    finally:
        capacity.release()
