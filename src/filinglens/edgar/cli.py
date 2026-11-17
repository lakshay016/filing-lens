"""``fl ingest`` and ``fl universe`` commands."""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path
from typing import Annotated

import httpx
import typer

from filinglens.config import get_settings
from filinglens.db.session import make_engine, session_factory
from filinglens.edgar.client import EdgarClient, EdgarConfigError, EdgarFetchError
from filinglens.edgar.fetch import IngestSummary
from filinglens.edgar.fetch import ingest as run_ingest
from filinglens.edgar.index import (
    TickerEntry,
    fetch_ticker_map,
    load_cached_ticker_map,
    sic_division,
)
from filinglens.edgar.universe import (
    UniverseError,
    load_universe,
    match_company_names,
    render_draft,
    resolve_ciks,
)

_DRAFT_OUT = Path("config/universes/t1_rag.draft.toml")

app = typer.Typer(no_args_is_help=True, help="EDGAR ingestion.")
universe_app = typer.Typer(no_args_is_help=True, help="Universe files.")

# TODO(author/lead): confirm this raw-file URL still resolves before the first real run.
# Found 2026-11-17 on github.com/patronus-ai/financebench (data/ holds this file); the
# download itself has not been exercised.
FINANCEBENCH_URL = (
    "https://raw.githubusercontent.com/patronus-ai/financebench/main/data/"
    "financebench_open_source.jsonl"
)


def _client() -> EdgarClient:
    try:
        return EdgarClient()
    except EdgarConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc


def _cache_dir() -> Path:
    return get_settings().data_dir / "cache" / "edgar"


@app.command()
def ingest(
    universe: str = typer.Option(..., "--universe", help="Universe name or TOML path."),
    since: int | None = typer.Option(None, "--since", help="Earliest fiscal year."),
    limit: int | None = typer.Option(None, "--limit", help="Download at most N filings."),
) -> None:
    """Build the filing manifest and download primary documents (resumable)."""
    client = _client()  # fails with exit 2 before any request
    try:
        uni = load_universe(universe)
    except UniverseError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    async def run() -> IngestSummary:
        engine = make_engine()
        try:
            async with client:
                return await run_ingest(
                    uni, session_factory(engine), client, since=since, limit=limit
                )
        finally:
            engine.dispose()

    try:
        summary = asyncio.run(run())
    except (UniverseError, EdgarFetchError, NotImplementedError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"companies {summary.companies} | filings seen {summary.filings_seen} | "
        f"new {summary.filings_new} | fetched {summary.fetched} | "
        f"skipped {summary.skipped} | failed {summary.failed} | "
        f"{summary.bytes / 1e6:.1f} MB"
    )
    if summary.failed:
        raise typer.Exit(1)


async def _ticker_map() -> dict[str, TickerEntry]:
    cached = load_cached_ticker_map(_cache_dir())
    if cached is not None:
        return cached
    client = _client()
    async with client:
        return await fetch_ticker_map(client, _cache_dir())


@universe_app.command("check")
def universe_check(name: str) -> None:
    """Resolve a universe's tickers and print one line per company."""
    try:
        uni = load_universe(name)
        ticker_map = asyncio.run(_ticker_map()) if uni.tickers else {}
        entries = resolve_ciks(uni, ticker_map)
    except (UniverseError, EdgarFetchError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    # SIC is not in the ticker map; the division is shown once a company has been ingested.
    sics = _known_sics(list(entries))
    for cik, entry in entries.items():
        division = sic_division(sics.get(cik)) or "-"
        typer.echo(f"{entry.ticker or '-':<8} {cik:>10}  {entry.title or '-'}  [{division}]")


def _known_sics(ciks: list[int]) -> dict[int, str | None]:
    """SIC codes already in the database, if it is reachable; otherwise empty."""
    import sqlalchemy as sa

    from filinglens.db.models import Company

    engine = make_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa.select(Company.cik, Company.sic).where(Company.cik.in_(ciks)))
            return {r.cik: r.sic for r in rows}
    except sa.exc.SQLAlchemyError:
        return {}
    finally:
        engine.dispose()


@universe_app.command("draft-t1")
def draft_t1(
    out: Annotated[Path, typer.Option("--out", help="Where to write the draft.")] = _DRAFT_OUT,
) -> None:
    """Draft the t1_rag universe from FinanceBench company names and the holdings file."""
    settings = get_settings()
    cache = settings.data_dir / "cache" / "financebench"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / "financebench_open_source.jsonl"
    # Plain client on purpose: the SEC contact User-Agent must never reach another host.
    response = httpx.get(FINANCEBENCH_URL, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    target.write_bytes(response.content)
    names = sorted(
        {
            str(json.loads(line)["company"]).strip()
            for line in response.text.splitlines()
            if line.strip()
        }
    )
    holdings_path = settings.holdings_file
    if not holdings_path.exists():
        holdings_path = Path("holdings.sample.toml")
    with holdings_path.open("rb") as handle:
        holdings = [str(t) for t in tomllib.load(handle).get("tickers", [])]
    ticker_map = asyncio.run(_ticker_map())
    text = render_draft(match_company_names(names, ticker_map), holdings, ticker_map)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    typer.echo(f"wrote {out} ({len(names)} FinanceBench companies, holdings from {holdings_path})")
