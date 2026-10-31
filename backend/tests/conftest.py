"""Tests run against a real PostGIS database (TEST_DATABASE_URL), never the operational one.

Locally: docker compose exec api pytest   (uses the rei_test database created on first start)
"""

import os

os.environ.setdefault(
    "TEST_DATABASE_URL", "postgresql+psycopg://rei:change-me@localhost:5432/rei_test"
)
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ["RATE_LIMIT_STORAGE"] = "memory://"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from alembic import command  # noqa: E402


@pytest.fixture(scope="session")
def migrated_db():
    """Apply all migrations once per test session on a clean schema."""
    from app.database.session import engine

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(Config("alembic.ini"), "head")
    yield engine


@pytest.fixture
def db(migrated_db):
    from app.database.session import SessionLocal

    with SessionLocal() as session:
        yield session
    with migrated_db.begin() as conn:
        conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.rate_limit import limiter
    from app.main import app

    limiter.reset()
    with TestClient(app) as c:
        yield c
