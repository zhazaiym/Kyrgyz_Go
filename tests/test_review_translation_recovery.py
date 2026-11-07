from datetime import timedelta

import pytest

from ML.errors import AIError
from mysite.database.db import SessionLocal
from mysite.database.models import About, TranslationJob
from mysite.translations import jobs


@pytest.mark.parametrize('code', ['ai_unavailable', 'ai_rate_limit', 'ai_timeout'])
def test_transient_errors_never_become_terminal_and_keep_diagnostic_code(
    client, monkeypatch, caplog, code
):
    now = jobs.utcnow()
    monkeypatch.setattr(jobs, 'utcnow', lambda: now)
    source = {'title': 'Transient recovery ' + code}
    with SessionLocal() as db:
        record = About(**source)
        db.add(record)
        db.commit()
        identity = record.id
    assert jobs.persist_translation_job(About, identity, source)

    def unavailable(values):
        raise AIError(code)

    for _ in range(12):
        result, delay = jobs._run_persisted_translation((About, identity), source, unavailable)
        assert result == code
        assert 0 < delay <= 3600
        now += timedelta(seconds=delay + 1)
    assert code in caplog.text
    with SessionLocal() as db:
        job = db.query(TranslationJob).filter_by(entity='abouts', record_id=identity).one()
        assert job.status == 'pending' and job.last_error == code
    result, delay = jobs._run_persisted_translation(
        (About, identity),
        source,
        lambda values: {language: dict(values) for language in ('en', 'de', 'zh')},
    )
    assert result == 'translated' and delay == 0


def test_failed_transient_jobs_recover_but_permanent_errors_stop(client, monkeypatch):
    now = jobs.utcnow()
    monkeypatch.setattr(jobs, 'utcnow', lambda: now)
    source = {'title': 'Permanent translation probe'}
    with SessionLocal() as db:
        record = About(**source)
        db.add(record)
        db.commit()
        identity = record.id
        db.add(
            TranslationJob(
                entity='abouts',
                record_id=identity,
                source=source,
                status='failed',
                attempts=5,
                last_error='ai_unavailable',
            )
        )
        db.commit()
    assert jobs.persist_translation_job(About, identity, source)
    for _ in range(3):
        result, delay = jobs._run_persisted_translation(
            (About, identity), source, lambda values: {}
        )
        now += timedelta(seconds=delay + 1)
    with SessionLocal() as db:
        job = db.query(TranslationJob).filter_by(entity='abouts', record_id=identity).one()
        assert job.status == 'failed' and job.last_error == 'invalid_translation'
    assert not jobs.persist_translation_job(About, identity, source)


def test_translation_quota_is_shared_across_concurrent_workers(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from mysite.api import rate_limit
    from mysite.translations.quota import reserve_translation_call

    monkeypatch.setenv('GEMINI_REQUESTS_PER_MINUTE', '2')
    monkeypatch.setattr(rate_limit, '_current_epoch', lambda: 1_987_654_320)

    def attempt(_):
        try:
            reserve_translation_call()
            return True
        except AIError as exc:
            assert exc.code == 'ai_rate_limit'
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(attempt, range(4)))
    assert sum(accepted) == 2
