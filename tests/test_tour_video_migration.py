from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
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
            with Session(engine) as db:
                tour = Tour(
                    title='Preserved migration tour', price=100, main_image='/media/old.webp'
                )
                db.add(tour)
                db.commit()
                identity = tour.id
            command.upgrade(config, 'head')
            with engine.begin() as connection:
                assert (
                    connection.scalar(text('SELECT version_num FROM alembic_version'))
                    == '20261109_0028'
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
