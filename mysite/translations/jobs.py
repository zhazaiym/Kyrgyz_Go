"""Best-effort catalogue translation after commit, without holding a DB connection."""

import logging
from threading import BoundedSemaphore

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, object_session

from mysite.database.db import SessionLocal
from mysite.database.models import Tour, TourTranslation

logger = logging.getLogger(__name__)
capacity = BoundedSemaphore(2)


def schedule_translation(record, fields, translator):
    session = object_session(record)
    if session is None:
        raise RuntimeError('Translation scheduling requires an attached record')
    source = {field: getattr(record, field) for field in fields}
    session.info.setdefault('catalogue_translation_jobs', {})[(type(record), id(record))] = (
        record,
        source,
        translator,
    )


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


def translate_record(entity, identity, source, translator):
    if not capacity.acquire(blocking=False):
        logger.warning('Catalogue translation capacity exhausted; keeping original text')
        return False
    try:
        # No database session is open while the external service is called.
        translated = translator(source)
        with SessionLocal() as db:
            record = db.get(entity, identity, with_for_update=True)
            if record is None or any(
                getattr(record, key) != value for key, value in source.items()
            ):
                return False
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
            elif not record.translations:
                record.translations = translated
            db.commit()
        return True
    except Exception:
        logger.exception('Catalogue translation failed; source record is already saved')
        return False
    finally:
        capacity.release()
