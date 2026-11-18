"""``fl compare`` command."""

from __future__ import annotations

import itertools
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from filinglens.compare.diff import diff_paragraphs
from filinglens.compare.load import FilingRef, filings_for, item_paragraphs
from filinglens.compare.render import PairView, RunInfo, pair_counts, render_page
from filinglens.config import get_settings
from filinglens.db.session import make_engine, session_factory
from filinglens.edgar.index import TickerEntry, load_cached_ticker_map
from filinglens.edgar.universe import UniverseError, load_universe, resolve_ciks

app = typer.Typer(no_args_is_help=True, help="Baseline comparison of one Item.")

_ITEM_TITLES = {"1A": "Item 1A Risk Factors"}
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


@app.command("compare")
def compare(
    universe: Annotated[str, typer.Option("--universe", help="Universe name or TOML path.")],
    item: Annotated[str, typer.Option("--item", help="Item code, for example 1A.")],
    out: Annotated[Path, typer.Option("--out", help="HTML file to write.")],
) -> None:
    """Write a static HTML page comparing consecutive annual reports for one Item."""
    try:
        uni = load_universe(universe)
        ticker_map: dict[str, TickerEntry] = {}
        if uni.tickers:
            cached = load_cached_ticker_map(get_settings().data_dir / "cache" / "edgar")
            if cached is None:
                raise UniverseError("no cached ticker map; run `fl ingest` for this universe first")
            ticker_map = dict(cached)
        ciks = list(resolve_ciks(uni, ticker_map))
    except UniverseError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    views: list[PairView] = []
    engine = make_engine()
    try:
        with session_factory(engine)() as session:
            refs = filings_for(session, uni, ciks)
            by_cik: dict[int, list[FilingRef]] = {}
            for ref in refs:
                by_cik.setdefault(ref.cik, []).append(ref)
            for filings in by_cik.values():
                for old, new in itertools.pairwise(filings):
                    old_paras = item_paragraphs(session, old.filing_id, item)
                    new_paras = item_paragraphs(session, new.filing_id, item)
                    label = f"{old.company} FY{old.fiscal_year} -> FY{new.fiscal_year}"
                    if old_paras is None or new_paras is None:
                        typer.echo(f"skipped {label}: Item {item} is not ok on both sides")
                        continue
                    ops = diff_paragraphs(old_paras, new_paras)
                    views.append(PairView(old, new, ops))
                    c = pair_counts(ops)
                    typer.echo(
                        f"{label}: equal {c.equal} | added {c.added} | removed {c.removed} | "
                        f"replaced groups {c.replaced_groups} "
                        f"(old {c.replaced_old} / new {c.replaced_new} paragraphs)"
                    )
    finally:
        engine.dispose()

    if not views:
        typer.echo("error: no pair could be built", err=True)
        raise typer.Exit(1)

    companies = {v.new.company for v in views}
    company = next(iter(companies)) if len(companies) == 1 else uni.name
    command = f"uv run fl compare --universe {universe} --item {item} --out {out}"
    info = RunInfo(generated=datetime.now(UTC), commit=_commit(), command=command)
    title = _ITEM_TITLES.get(item, f"Item {item}")
    page = render_page(company, views, info, title)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    typer.echo(f"wrote {out}")
