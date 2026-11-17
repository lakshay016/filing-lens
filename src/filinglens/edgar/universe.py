"""Universe files (SPEC §4) and the name matching used to draft ``t1_rag``."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from filinglens.edgar.index import TickerEntry

# src/filinglens/edgar/universe.py -> repository root
_ROOT = Path(__file__).resolve().parents[3]
UNIVERSE_DIR = _ROOT / "config" / "universes"


class UniverseError(ValueError):
    """A universe file is malformed or names a ticker that is not in the SEC list."""


@dataclass(frozen=True, slots=True)
class Universe:
    name: str
    forms: tuple[str, ...]
    fiscal_year_min: int
    fiscal_year_max: int | None
    store_raw: bool
    tickers: tuple[str, ...]
    ciks: tuple[int, ...]


def load_universe(name_or_path: str) -> Universe:
    if name_or_path.endswith(".toml") or "/" in name_or_path:
        path = Path(name_or_path)
    else:
        path = UNIVERSE_DIR / f"{name_or_path}.toml"
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise UniverseError(f"universe file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise UniverseError(f"{path}: invalid TOML: {exc}") from exc
    try:
        forms = tuple(str(f) for f in data["forms"])
        year_max = data.get("fiscal_year_max")
        universe = Universe(
            name=str(data.get("name", path.stem)),
            forms=forms,
            fiscal_year_min=int(data["fiscal_year_min"]),
            fiscal_year_max=int(year_max) if year_max is not None else None,
            store_raw=bool(data.get("store_raw", True)),
            tickers=tuple(str(t).strip().upper() for t in data.get("tickers", [])),
            ciks=tuple(int(c) for c in data.get("ciks", [])),
        )
    except KeyError as exc:
        raise UniverseError(f"{path}: missing key {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise UniverseError(f"{path}: bad value: {exc}") from exc
    if not universe.forms:
        raise UniverseError(f"{path}: forms is empty")
    if not universe.tickers and not universe.ciks:
        raise UniverseError(f"{path}: no tickers or ciks")
    return universe


def resolve_ciks(
    universe: Universe, ticker_map: Mapping[str, TickerEntry]
) -> dict[int, TickerEntry]:
    """CIK to ticker entry. Explicit CIKs not found in the map get an empty-ticker entry."""
    by_cik: dict[int, TickerEntry] = {}
    for ticker in universe.tickers:
        entry = ticker_map.get(ticker.upper())
        if entry is None:
            raise UniverseError(f"unknown ticker {ticker!r}: not in the SEC ticker list")
        by_cik.setdefault(entry.cik, entry)
    known = {e.cik: e for e in ticker_map.values()}
    for cik in universe.ciks:
        by_cik.setdefault(cik, known.get(cik, TickerEntry(cik=cik, ticker="", title="")))
    return by_cik


# ---- FinanceBench name matching (pure) -------------------------------------------------

_SUFFIXES = frozenset(
    {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "PLC", "HOLDINGS", "GROUP", "THE"}
)


def normalise_company_name(name: str) -> str:
    tokens = re.sub(r"[^A-Z0-9]+", " ", name.upper()).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)


@dataclass(frozen=True, slots=True)
class NameMatch:
    name: str
    entry: TickerEntry | None  # None = unresolved
    reason: str = ""  # why unresolved


def match_company_names(
    names: Iterable[str], ticker_map: Mapping[str, TickerEntry]
) -> list[NameMatch]:
    """Exact match on normalised names only. Ambiguity (different CIKs) is unresolved."""
    index: dict[str, list[TickerEntry]] = {}
    for entry in ticker_map.values():
        key = normalise_company_name(entry.title)
        if key:
            index.setdefault(key, []).append(entry)
    results: list[NameMatch] = []
    for name in names:
        candidates = index.get(normalise_company_name(name), [])
        if not candidates:
            results.append(NameMatch(name, None, "no SEC company with that normalised name"))
        elif len({c.cik for c in candidates}) > 1:
            tickers = ", ".join(c.ticker for c in candidates)
            results.append(NameMatch(name, None, f"ambiguous: {tickers}"))
        else:
            results.append(NameMatch(name, candidates[0]))
    return results


def render_draft(
    matches: list[NameMatch],
    holdings: Iterable[str],
    ticker_map: Mapping[str, TickerEntry],
    *,
    fiscal_year_min: int = 2014,
) -> str:
    """Text of a draft universe file. Nothing is guessed: unmatched names are commented."""
    lines = [
        "# DRAFT t1_rag universe, written by `fl universe draft-t1`.",
        "# Review every line, resolve the unmatched names at the end, then save as t1_rag.toml.",
        'name = "t1_rag"',
        'forms = ["10-K", "10-K405"]',
        f"fiscal_year_min = {fiscal_year_min}",
        "store_raw = true",
        "tickers = [",
    ]
    seen: set[str] = set()
    for m in matches:
        if m.entry is not None and m.entry.ticker not in seen:
            seen.add(m.entry.ticker)
            lines.append(f'  "{m.entry.ticker}",  # FinanceBench: {m.name} -> SEC: {m.entry.title}')
    unknown_holdings: list[str] = []
    for ticker in holdings:
        t = ticker.strip().upper()
        if t in seen:
            continue
        if t in ticker_map:
            seen.add(t)
            lines.append(f'  "{t}",  # holdings -> SEC: {ticker_map[t].title}')
        else:
            unknown_holdings.append(t)
    lines.append("]")
    unresolved = [m for m in matches if m.entry is None]
    if unresolved or unknown_holdings:
        lines.append("")
        lines.append("# Unresolved: add the ticker to the list above by hand, or drop the company.")
        for m in unresolved:
            lines.append(f"#   {m.name}  ({m.reason})")
        for t in unknown_holdings:
            lines.append(f"#   holdings ticker {t}  (not in the SEC ticker list)")
    return "\n".join(lines) + "\n"
