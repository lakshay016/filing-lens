from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from filinglens.edgar.index import (
    document_url,
    fiscal_year_of,
    parse_company_tickers,
    parse_submissions,
    parse_submissions_page,
    sic_division,
)

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "edgar"


def load(name: str) -> object:
    return json.loads((FIX / name).read_text())


def test_company_tickers() -> None:
    m = parse_company_tickers(load("company_tickers.json"))
    assert set(m) == {"AAPL", "XOM", "JPM", "COST", "BA"}
    assert m["AAPL"].cik == 320193
    assert m["XOM"].title == "EXXON MOBIL CORP"


def test_company_tickers_duplicate_keeps_first() -> None:
    payload = {
        "0": {"cik_str": 1, "ticker": "abc", "title": "First"},
        "1": {"cik_str": 2, "ticker": "ABC", "title": "Second"},
    }
    m = parse_company_tickers(payload)
    assert m["ABC"].cik == 1


def test_submissions_main() -> None:
    info, metas, pages = parse_submissions(load("submissions_main.json"))
    assert (info.cik, info.name, info.ticker, info.sic) == (320193, "Apple Inc.", "AAPL", "3571")
    assert info.sector == "Manufacturing"
    assert pages == ["CIK0000320193-submissions-001.json"]
    by_acc = {m.accession: m for m in metas}
    # 10-Q and 8-K dropped; 10-K with empty primaryDocument dropped.
    assert {m.form for m in metas} == {"10-K", "10-K/A"}
    assert "0000320193-18-000145" not in by_acc
    assert len(metas) == 7
    k = by_acc["0000320193-23-000106"]
    assert k.fiscal_year == 2023
    assert k.period_of_report == date(2023, 9, 30)
    assert k.filed_date == date(2023, 11, 3)
    assert k.primary_document == "aapl-20230930.htm"


def test_acceptance_is_utc_aware() -> None:
    _, metas, _ = parse_submissions(load("submissions_main.json"))
    k = next(m for m in metas if m.accession == "0000320193-24-000123")
    assert k.accepted_at == datetime(2024, 11, 1, 18, 4, 25, tzinfo=UTC)
    assert k.accepted_at is not None
    assert k.accepted_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_empty_acceptance_and_report_date() -> None:
    _, metas, _ = parse_submissions(load("submissions_main.json"))
    by_acc = {m.accession: m for m in metas}
    assert by_acc["0000320193-20-000096"].accepted_at is None
    no_report = by_acc["0000320193-19-000119"]
    assert no_report.period_of_report is None
    assert no_report.fiscal_year is None


def test_submissions_page() -> None:
    metas = parse_submissions_page(load("submissions_page.json"), 320193)
    assert len(metas) == 5  # the 10-Q is dropped
    assert {m.cik for m in metas} == {320193}
    assert sorted(m.fiscal_year for m in metas if m.fiscal_year) == [2013, 2014, 2015, 2016, 2017]


@pytest.mark.parametrize(
    ("d", "year"),
    [
        (date(2023, 9, 30), 2023),
        (date(2022, 1, 1), 2021),
        (date(2022, 1, 7), 2021),
        (date(2022, 1, 8), 2022),
        (date(2022, 12, 31), 2022),
        (date(2024, 1, 28), 2024),
    ],
)
def test_fiscal_year_of(d: date, year: int) -> None:
    assert fiscal_year_of(d) == year


@pytest.mark.parametrize(
    ("sic", "division"),
    [
        ("3571", "Manufacturing"),
        ("0100", "Agriculture"),
        ("1311", "Mining"),
        ("1500", "Construction"),
        ("4911", "Transportation & Utilities"),
        ("5045", "Wholesale Trade"),
        ("5400", "Retail Trade"),
        ("6021", "Finance, Insurance & Real Estate"),
        ("7372", "Services"),
        ("9100", "Public Administration"),
        ("1900", None),
        ("", None),
        (None, None),
        ("ab12", None),
    ],
)
def test_sic_division(sic: str | None, division: str | None) -> None:
    assert sic_division(sic) == division


def test_document_url() -> None:
    assert document_url(320193, "0000320193-23-000106", "aapl-20230930.htm") == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
    )
