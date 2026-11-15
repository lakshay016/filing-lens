from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from filinglens.config import Settings, get_settings

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FL_LLM_MODE", "replay")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Fresh settings that never read the real ``.env``."""
    return Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Engine on a fresh ``filinglens_test`` database, migrated to head."""
    cfg = Settings()  # real environment: CI and the author set FL_DATABASE_URL
    if not cfg.is_local_database():
        pytest.exit("Refusing to run tests against a non-local database.", returncode=2)
    test_url = cfg.test_database_url()
    admin_url = urlunsplit(urlsplit(cfg.database_url)._replace(path="/postgres"))
    admin_sa = admin_url.replace("postgresql://", "postgresql+psycopg://", 1)
    test_sa = test_url.replace("postgresql://", "postgresql+psycopg://", 1)

    admin = create_engine(admin_sa, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS filinglens_test WITH (FORCE)"))
            conn.execute(text("CREATE DATABASE filinglens_test"))
    except OperationalError as exc:
        admin.dispose()
        host = urlsplit(cfg.database_url)
        where = f"{host.hostname}:{host.port}"
        if os.environ.get("FL_REQUIRE_DB") == "1":
            pytest.fail(f"local Postgres not reachable on {where}: {exc}", pytrace=False)
        pytest.skip(f"local Postgres not reachable on {where}; run docker compose up -d")

    alembic_cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", test_sa)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_sa, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS filinglens_test WITH (FORCE)"))
        admin.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is rolled back after the test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
