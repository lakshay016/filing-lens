"""Synchronous SQLAlchemy engine and session helpers (psycopg 3)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from filinglens.config import get_settings


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().sqlalchemy_url(), pool_pre_ping=True)


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(engine or make_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error."""
    engine = make_engine()
    session = session_factory(engine)()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
