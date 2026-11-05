"""Back up and replace the About catalogue with the approved eight-slide story."""

import argparse
import json
import sys
from pathlib import Path

from mysite.about_content import ABOUT_DESCRIPTION, ABOUT_SLIDES, ABOUT_TITLE
from mysite.database.db import SessionLocal
from mysite.database.models import About, AboutSection
from mysite.translations.content import update_translations
from mysite.translations.jobs import (_translation_is_complete, committed_jobs, enqueue_translation,
                                      translation_queue)


def _record_payload(record):
    return {column.key: getattr(record, column.key) for column in record.__table__.columns}


def _backup_rows(db):
    return {
        'abouts': [_record_payload(row) for row in db.query(About).order_by(About.id).all()],
        'about_sections': [
            _record_payload(row)
            for row in db.query(AboutSection).order_by(AboutSection.order, AboutSection.id).all()
        ],
    }


def replace_content(backup_path: Path, *, apply: bool) -> tuple[int, int, int]:
    if apply and backup_path.exists():
        raise FileExistsError(f'Refusing to overwrite backup: {backup_path}')

    db = SessionLocal()
    try:
        old_rows = _backup_rows(db)
        print(
            f'Current records: {len(old_rows["abouts"])} About, '
            f'{len(old_rows["about_sections"])} AboutSection; '
            f'new records: 1 About, {len(ABOUT_SLIDES)} AboutSection.'
        )
        if not apply:
            return len(old_rows['abouts']), len(old_rows['about_sections']), 0

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps(old_rows, ensure_ascii=False, indent=2), encoding='utf-8')

        db.query(AboutSection).delete(synchronize_session=False)
        db.query(About).delete(synchronize_session=False)

        about = About(title=ABOUT_TITLE, description=ABOUT_DESCRIPTION, image=None, is_active=True)
        db.add(about)
        update_translations(about)

        sections = []
        for order, slide in enumerate(ABOUT_SLIDES, start=1):
            section = AboutSection(order=order, is_active=True, **slide)
            db.add(section)
            update_translations(section)
            sections.append(section)

        # An ORM insert listener initially assigns order=id, so reset the
        # requested display order after IDs have been created.
        db.flush()
        for order, section in enumerate(sections, start=1):
            section.order = order

        db.commit()
        jobs = committed_jobs(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    queued = sum(bool(enqueue_translation(*job)) for job in jobs)
    if queued:
        translation_queue.join()

    with SessionLocal() as verify_db:
        current_about = verify_db.query(About).filter(About.is_active.is_(True)).all()
        current_sections = (
            verify_db.query(AboutSection)
            .filter(AboutSection.is_active.is_(True))
            .order_by(AboutSection.order, AboutSection.id)
            .all()
        )
        complete = sum(
            _translation_is_complete(
                row.translations, {'title': row.title, 'description': row.description}
            )
            for row in [*current_about, *current_sections]
        )

    print(
        f'Replaced with {len(current_about)} active About and '
        f'{len(current_sections)} active AboutSection records; '
        f'{sum(bool(section.image) for section in current_sections)} slide images; '
        f'{queued} translation jobs queued; {complete}/{len(current_about) + len(current_sections)} '
        'records have complete translations.'
    )
    return len(old_rows['abouts']), len(old_rows['about_sections']), queued


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='replace database records')
    parser.add_argument('--backup', type=Path, help='new JSON backup path required with --apply')
    options = parser.parse_args(argv)
    if options.apply and options.backup is None:
        parser.error('--backup is required with --apply')
    backup_path = options.backup or Path('/tmp/about-content-backup.json')
    replace_content(backup_path, apply=options.apply)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'About content replacement failed: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc
