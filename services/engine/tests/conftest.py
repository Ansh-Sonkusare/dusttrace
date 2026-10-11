import os

import pytest

from dusttrace import db
from dusttrace.config import Settings, load_seed


@pytest.fixture(scope="session")
def db_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; database tests run in CI")
    return url


@pytest.fixture
def conn(db_url):
    """A freshly migrated and seeded database. Wipes the public schema, so never point it at real data."""
    c = db.connect(db_url)
    c.execute("drop schema if exists public cascade")
    c.execute("create schema public")
    c.commit()
    db.migrate(c)
    db.upsert_seed(c, load_seed())
    yield c
    c.close()


@pytest.fixture
def settings(db_url):
    return Settings(database_url=db_url, openaq_api_key=None, ward_id="K-East")
