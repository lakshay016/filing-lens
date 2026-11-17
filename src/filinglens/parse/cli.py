"""``fl parse`` command."""

from __future__ import annotations

import typer

from filinglens.config import get_settings
from filinglens.db.session import make_engine, session_factory
from filinglens.edgar.index import TickerEntry, load_cached_ticker_map
from filinglens.edgar.universe import UniverseError, load_universe, resolve_ciks
from filinglens.parse.pipeline import build_report, parse_universe

app = typer.Typer(no_args_is_help=True, help="Parse stored filings.")


def _ciks(name: str) -> list[int]:
    uni = load_universe(name)
    ticker_map: dict[str, TickerEntry] = {}
    if uni.tickers:
        cached = load_cached_ticker_map(get_settings().data_dir / "cache" / "edgar")
        if cached is None:
            raise UniverseError("no cached ticker map; run `fl ingest` for this universe first")
        ticker_map = dict(cached)
    return list(resolve_ciks(uni, ticker_map))


@app.command("parse")
def parse(
    universe: str = typer.Option(..., "--universe", help="Universe name or TOML path."),
    force: bool = typer.Option(False, "--force", help="Re-parse filings already parsed."),
    limit: int | None = typer.Option(None, "--limit", help="Parse at most N filings."),
    report: bool = typer.Option(False, "--report", help="Print the report only."),
) -> None:
    """Segment stored filings into Items, then print the status report."""
    try:
        ciks = _ciks(universe)
    except UniverseError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    engine = make_engine()
    try:
        factory = session_factory(engine)
        if not report:
            summary = parse_universe(
                factory, ciks, get_settings().data_dir, force=force, limit=limit
            )
            typer.echo(
                f"selected {summary.selected} | ok {summary.ok} | "
                f"partial {summary.partial} | failed {summary.failed}\n"
            )
        with factory() as session:
            typer.echo(build_report(session, ciks))
    finally:
        engine.dispose()
