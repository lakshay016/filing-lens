"""Root command-line interface (``fl``)."""

from __future__ import annotations

import logging

import typer

import filinglens
from filinglens.config import get_settings
from filinglens.db import cli as db_cli
from filinglens.edgar import cli as edgar_cli

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Filing Lens")

# Later tasks register their sub-apps here, one line each, for example:
# app.add_typer(edgar_cli.app, name="edgar")
app.add_typer(db_cli.app, name="db")
app.add_typer(edgar_cli.app)  # no name: registers `fl ingest` at the top level
app.add_typer(edgar_cli.universe_app, name="universe")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Log at DEBUG level."),
) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(filinglens.__version__)


@app.command()
def env() -> None:
    """Show which settings are filled in (secrets appear only as set / not set)."""
    info = get_settings().describe()
    width = max(len(k) for k in info)
    for key, value in info.items():
        typer.echo(f"{key.ljust(width)}: {value}")
