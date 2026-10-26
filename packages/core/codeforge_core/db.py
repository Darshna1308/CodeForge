from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(
        url or get_settings().database_url,
        pool_size=10,
        max_overflow=10,
        pool_pre_ping=True,  # survive Postgres restarts without surfacing stale-connection errors
        pool_recycle=1800,
    )


@lru_cache
def get_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """Unit of work: commit on success, roll back on any exception."""
    session = get_sessionmaker(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
