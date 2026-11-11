import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from mysite.database import db as database
from mysite.database.models import Tour
from tests.postgres_support import temporary_database


def test_upgrade_and_downgrade_preserve_existing_tours(monkeypatch):
    with temporary_database() as url:
        monkeypatch.setattr(database, 'DATABASE_URL', url)
        config = Config('alembic.ini')
        command.upgrade(config, '20261107_0027')
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                identity = connection.scalar(
                    Tour.__table__.insert()
                    .values(
                        title='Preserved migration tour', price=100, main_image='/media/old.webp'
                    )
                    .returning(Tour.id)
                )
            command.upgrade(config, 'head')
            with engine.begin() as connection:
                assert (
                    connection.scalar(text('SELECT version_num FROM alembic_version'))
                    == ScriptDirectory.from_config(config).get_current_head()
                )
                assert (
                    connection.scalar(
                        text('SELECT main_image FROM tours WHERE id=:id'), {'id': identity}
                    )
                    == '/media/old.webp'
                )
                connection.execute(
                    text('INSERT INTO tour_videos (tour_id, video_url) VALUES (:id, :url)'),
                    {'id': identity, 'url': '/media/video.mp4'},
                )
            assert 'tour_videos' in inspect(engine).get_table_names()
            command.downgrade(config, '20261107_0027')
            assert 'tour_videos' not in inspect(engine).get_table_names()
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text('SELECT title FROM tours WHERE id=:id'), {'id': identity}
                    )
                    == 'Preserved migration tour'
                )
            command.upgrade(config, 'head')
        finally:
            engine.dispose()


@pytest.mark.parametrize('starting_revision', ['20261109_0030', '20261109_0028'])
def test_merge_upgrade_preserves_data_from_both_branches(monkeypatch, starting_revision):
    with temporary_database() as url:
        monkeypatch.setattr(database, 'DATABASE_URL', url)
        config = Config('alembic.ini')
        command.upgrade(config, starting_revision)
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                identity = connection.scalar(
                    Tour.__table__.insert()
                    .values(title='Existing branch tour', price=100)
                    .returning(Tour.id)
                )
                if starting_revision == '20261109_0030':
                    connection.execute(
                        text('UPDATE tours SET video_url=:url WHERE id=:id'),
                        {'id': identity, 'url': 'https://example.com/existing-video'},
                    )
                else:
                    connection.execute(
                        text('INSERT INTO tour_videos (tour_id, video_url) VALUES (:id, :url)'),
                        {'id': identity, 'url': '/media/existing-video.mp4'},
                    )
            command.upgrade(config, 'head')
            command.check(config)
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text('SELECT title FROM tours WHERE id=:id'), {'id': identity}
                    )
                    == 'Existing branch tour'
                )
                if starting_revision == '20261109_0030':
                    assert (
                        connection.scalar(
                            text('SELECT video_url FROM tours WHERE id=:id'), {'id': identity}
                        )
                        == 'https://example.com/existing-video'
                    )
                else:
                    assert (
                        connection.scalar(
                            text('SELECT video_url FROM tour_videos WHERE tour_id=:id'),
                            {'id': identity},
                        )
                        == '/media/existing-video.mp4'
                    )
        finally:
            engine.dispose()
