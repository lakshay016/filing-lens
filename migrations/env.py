"""Alembic environment. Refuses to run against a non-local database by default."""

from __future__ import annotations

import os
from logging.config import fileConfig
from urllib.parse import urlsplit

from alembic import context
from sqlalchemy import create_engine, pool

from filinglens.config import get_settings
from filinglens.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().sqlalchemy_url()


def _guard(url: str) -> None:
    host = urlsplit(url).hostname
    if host not in _LOCAL_HOSTS and os.environ.get("FL_ALLOW_REMOTE_MIGRATION") != "1":
        raise RuntimeError(
            f"Refusing to migrate non-local database host {host!r}. "
            "Set FL_ALLOW_REMOTE_MIGRATION=1 to override."
        )


def run_migrations_offline() -> None:
    url = _database_url()
    _guard(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    _guard(url)
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
