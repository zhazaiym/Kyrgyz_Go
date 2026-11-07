import os
import time

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from mysite.api.observability import record_database_query

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


def _statement_category(statement):
    operation = statement.lstrip().split(None, 1)[0].lower() if statement.strip() else 'other'
    if operation in {'select', 'insert', 'update', 'delete'}:
        return operation
    if operation in {'create', 'alter', 'drop', 'truncate', 'grant', 'revoke'}:
        return 'ddl'
    return 'other'


def _record_statement(connection, statement, outcome):
    starts = connection.info.get('kerben_query_started', [])
    if not starts:
        return
    started = starts.pop()
    record_database_query(_statement_category(statement), outcome, time.perf_counter() - started)


@event.listens_for(engine, 'before_cursor_execute')
def _start_statement_timer(connection, cursor, statement, parameters, context, executemany):
    connection.info.setdefault('kerben_query_started', []).append(time.perf_counter())


@event.listens_for(engine, 'after_cursor_execute')
def _finish_statement_timer(connection, cursor, statement, parameters, context, executemany):
    _record_statement(connection, statement, 'success')


@event.listens_for(engine, 'handle_error')
def _fail_statement_timer(exception_context):
    connection = exception_context.connection
    if connection is not None and exception_context.statement:
        _record_statement(connection, exception_context.statement, 'failure')


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
