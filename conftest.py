"""Shared test setup: a dedicated Postgres database and Redis DB, migrated and seeded once.

Tests talk to real Postgres and Redis (and Docker for sandbox tests); nothing
is mocked. Point TEST_DATABASE_URL / TEST_REDIS_URL elsewhere if needed.
"""

import os

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://codeforge:codeforge@localhost:5432/codeforge_test")
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("RATE_LIMIT_SUBMIT", "5/60")
os.environ.setdefault("RATE_LIMIT_AUTH", "1000/60")
os.environ.setdefault("RATE_LIMIT_RUN", "1000/60")
os.environ.setdefault("LEASE_SECONDS", "30")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="session", autouse=True)
def database():
    from codeforge_core.db import get_engine
    from codeforge_core.redis_client import get_redis

    cfg = Config(os.path.join(ROOT, "apps/api/alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "apps/api/alembic"))
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    command.upgrade(cfg, "head")
    get_redis().flushdb()

    from codeforge_api.seed.__main__ import seed

    seed()
    yield
