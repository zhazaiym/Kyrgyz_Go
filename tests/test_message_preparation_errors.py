"""A preparation failure must not leave an unhandled turn in persistent history."""

import pytest
from sqlalchemy.orm import Query

from mysite.api import chat_service
from mysite.database.chat_models import ChatMessage
from mysite.database.db import SessionLocal
from tests.test_ml_booking_hardening import account_session


def test_history_load_failure_rolls_back_new_user_message(client, monkeypatch):
    token, identity, sid = account_session(client, 'history_load_failure')
    original_all = Query.all

    def failing_history(query):
        if any(item.get('entity') is ChatMessage for item in query.column_descriptions):
            raise RuntimeError('history load failed')
        return original_all(query)

    with monkeypatch.context() as scoped:
        scoped.setattr(Query, 'all', failing_history)
        with pytest.raises(RuntimeError, match='history load failed'):
            chat_service._prepare_message(sid, identity, token, 'Uncommitted question')

    with SessionLocal() as db:
        assert db.query(ChatMessage).filter_by(session_id=sid, role='user').count() == 0


def test_prepared_history_remains_readable_after_commit_and_session_close(client):
    token, identity, sid = account_session(client, 'detached_prepared_history')
    prepared = chat_service._prepare_message(sid, identity, token, 'Question')
    assert [(turn.role, bool(turn.content)) for turn in prepared[2]] == [('assistant', True)]
    with SessionLocal() as db:
        assert (
            db.query(ChatMessage).filter_by(session_id=sid, role='user').one().content == 'Question'
        )
