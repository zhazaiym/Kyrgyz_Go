import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
if not DATABASE_URL:
    raise RuntimeError('DATABASE_URL is required; configure a PostgreSQL connection in .env')
try:
    database_url = make_url(DATABASE_URL)
except (ValueError, TypeError) as exc:
    raise RuntimeError('DATABASE_URL must be a valid PostgreSQL URL') from exc
if database_url.get_backend_name() != 'postgresql':
    raise RuntimeError('Only PostgreSQL is supported; configure DATABASE_URL')
if database_url.drivername == 'postgresql':
    database_url = database_url.set(drivername='postgresql+psycopg2')

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    pool_timeout=5,
    connect_args={
        'connect_timeout': 5,
        'options': '-c statement_timeout=15000 -c lock_timeout=5000',
    },
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        from mysite.translations.jobs import committed_jobs, enqueue_translation

        jobs = committed_jobs(db)
        db.close()
        for job in jobs:
            enqueue_translation(*job)
