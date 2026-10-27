"""Disposable PostgreSQL databases; never migrate or clean the configured app DB."""

import os
from contextlib import contextmanager
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@contextmanager
def temporary_database():
    configured = (
        os.getenv('TEST_DATABASE_URL')
        or os.getenv('DATABASE_URL')
        or dotenv_values('.env').get('DATABASE_URL')
    )
    if not configured:
        raise RuntimeError('Set TEST_DATABASE_URL to PostgreSQL with CREATEDB permission')
    url = make_url(configured)
    if url.get_backend_name() != 'postgresql':
        raise RuntimeError('Tests require PostgreSQL')
    name = 'test_kyrgyzgo_' + uuid4().hex
    maintenance = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    try:
        with maintenance.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            yield url.set(database=name).render_as_string(hide_password=False)
        finally:
            # Only the generated database is ever dropped; FORCE closes test pools.
            assert name.startswith('test_kyrgyzgo_') and len(name) == 46
            with maintenance.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    finally:
        maintenance.dispose()
