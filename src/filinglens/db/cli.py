"""``fl db`` commands."""

from __future__ import annotations

from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from filinglens.db.session import make_engine

app = typer.Typer(no_args_is_help=True, help="Database commands.")

# src/filinglens/db/cli.py -> repository root
_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


@app.command()
def upgrade() -> None:
    """Apply all migrations (alembic upgrade head)."""
    command.upgrade(_alembic_config(), "head")


@app.command()
def status() -> None:
    """Print the current revision and whether it is head."""
    head = ScriptDirectory.from_config(_alembic_config()).get_current_head()
    engine = make_engine()
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()
    typer.echo(f"current: {current or '(none)'}")
    typer.echo(f"head:    {head}")
    typer.echo("up to date" if current == head else "not at head")
