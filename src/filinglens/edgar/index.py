"""Parsing of EDGAR index documents: ticker map and per-company submissions (SPEC §5.1)."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from filinglens.edgar.client import EdgarClient

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
TICKERS_CACHE_NAME = "company_tickers.json"

KEPT_FORMS = frozenset({"10-K", "10-K405", "10-K/A", "10-K405/A", "10-KT", "10-KT/A"})


@dataclass(frozen=True, slots=True)
class TickerEntry:
    cik: int
    ticker: str
    title: str


@dataclass(frozen=True, slots=True)
class CompanyInfo:
    cik: int
    name: str
    ticker: str | None
    sic: str | None
    sector: str | None


@dataclass(frozen=True, slots=True)
class FilingMeta:
    cik: int
    accession: str
    form: str
    period_of_report: date | None
    fiscal_year: int | None
    filed_date: date
    accepted_at: datetime | None  # timezone-aware UTC
    primary_document: str


def fiscal_year_of(period_of_report: date) -> int:
    """Calendar year of the period end, minus one when it falls on 1-7 January."""
    if period_of_report.month == 1 and period_of_report.day <= 7:
        return period_of_report.year - 1
    return period_of_report.year


_SIC_DIVISIONS: tuple[tuple[int, int, str], ...] = (
    (1, 9, "Agriculture"),
    (10, 14, "Mining"),
    (15, 17, "Construction"),
    (20, 39, "Manufacturing"),
    (40, 49, "Transportation & Utilities"),
    (50, 51, "Wholesale Trade"),
    (52, 59, "Retail Trade"),
    (60, 67, "Finance, Insurance & Real Estate"),
    (70, 89, "Services"),
    (91, 99, "Public Administration"),
)


def sic_division(sic: str | None) -> str | None:
    if not sic:
        return None
    prefix = sic.strip()[:2]
    if len(prefix) != 2 or not prefix.isdigit():
        return None
    n = int(prefix)
    for lo, hi, name in _SIC_DIVISIONS:
        if lo <= n <= hi:
            return name
    return None


def document_url(cik: int, accession: str, primary_document: str) -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession.replace('-', '')}/{primary_document}"
    )


def parse_company_tickers(payload: Any) -> dict[str, TickerEntry]:
    """Map upper-case ticker to entry; the first occurrence of a ticker wins."""
    result: dict[str, TickerEntry] = {}
    values = payload.values() if isinstance(payload, dict) else payload
    for item in values:
        ticker = str(item["ticker"]).strip().upper()
        if ticker and ticker not in result:
            result[ticker] = TickerEntry(
                cik=int(item["cik_str"]), ticker=ticker, title=str(item["title"])
            )
    return result


def _parse_accepted(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_columns(cols: Any, cik: int) -> list[FilingMeta]:
    """Parse one columnar object (``filings.recent`` or an older page)."""
    filings: list[FilingMeta] = []
    accessions = cols.get("accessionNumber", [])
    for i, accession in enumerate(accessions):
        form = cols["form"][i]
        if form not in KEPT_FORMS:
            continue
        primary = cols["primaryDocument"][i]
        if not primary:
            continue
        report = cols["reportDate"][i]
        period = date.fromisoformat(report) if report else None
        filings.append(
            FilingMeta(
                cik=cik,
                accession=accession,
                form=form,
                period_of_report=period,
                fiscal_year=fiscal_year_of(period) if period else None,
                filed_date=date.fromisoformat(cols["filingDate"][i]),
                accepted_at=_parse_accepted(cols["acceptanceDateTime"][i]),
                primary_document=primary,
            )
        )
    return filings


def parse_submissions(payload: Any) -> tuple[CompanyInfo, list[FilingMeta], list[str]]:
    cik = int(payload["cik"])
    tickers = payload.get("tickers") or []
    sic = payload.get("sic") or None
    info = CompanyInfo(
        cik=cik,
        name=str(payload["name"]),
        ticker=str(tickers[0]).upper() if tickers else None,
        sic=sic,
        sector=sic_division(sic),
    )
    filings = payload.get("filings", {})
    metas = _parse_columns(filings.get("recent", {}), cik)
    pages = [str(f["name"]) for f in filings.get("files", [])]
    return info, metas, pages


def parse_submissions_page(payload: Any, cik: int) -> list[FilingMeta]:
    return _parse_columns(payload, cik)


def load_cached_ticker_map(
    cache_dir: Path, max_age_hours: float = 24
) -> dict[str, TickerEntry] | None:
    """The cached ticker map if the cache file exists and is young enough, else None."""
    path = cache_dir / TICKERS_CACHE_NAME
    try:
        age = time.time() - path.stat().st_mtime
        if age > max_age_hours * 3600:
            return None
        return parse_company_tickers(json.loads(path.read_bytes()))
    except (OSError, ValueError, KeyError, TypeError):
        return None


async def fetch_ticker_map(
    client: EdgarClient, cache_dir: Path, max_age_hours: float = 24
) -> dict[str, TickerEntry]:
    cached = load_cached_ticker_map(cache_dir, max_age_hours)
    if cached is not None:
        return cached
    raw = await client.get_bytes(TICKERS_URL)
    result = parse_company_tickers(json.loads(raw))
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / (TICKERS_CACHE_NAME + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, cache_dir / TICKERS_CACHE_NAME)
    return result


async def fetch_filing_list(client: EdgarClient, cik: int) -> tuple[CompanyInfo, list[FilingMeta]]:
    """All kept-form filings of a company: the recent block plus every older page."""
    payload = await client.get_json(SUBMISSIONS_URL.format(cik=cik))
    info, metas, pages = parse_submissions(payload)
    seen = {m.accession for m in metas}
    for name in pages:
        page = await client.get_json(SUBMISSIONS_PAGE_URL.format(name=name))
        for meta in parse_submissions_page(page, cik):
            if meta.accession not in seen:
                seen.add(meta.accession)
                metas.append(meta)
    return info, metas
