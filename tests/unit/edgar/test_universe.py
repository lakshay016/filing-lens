from __future__ import annotations

import json
from pathlib import Path

import pytest

from filinglens.edgar.index import TickerEntry, parse_company_tickers
from filinglens.edgar.universe import (
    UniverseError,
    load_universe,
    match_company_names,
    normalise_company_name,
    render_draft,
    resolve_ciks,
)

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "edgar"


def ticker_map() -> dict[str, TickerEntry]:
    return parse_company_tickers(json.loads((FIX / "company_tickers.json").read_text()))


def write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "u.toml"
    p.write_text(body)
    return str(p)


def test_load_sample() -> None:
    u = load_universe("sample")
    assert u.name == "sample"
    assert u.forms == ("10-K", "10-K405")
    assert u.fiscal_year_min == 2018
    assert u.fiscal_year_max is None
    assert u.store_raw is True
    assert u.tickers[0] == "AAPL"
    assert u.ciks == ()


def test_unknown_ticker(tmp_path: Path) -> None:
    u = load_universe(
        write(tmp_path, 'forms=["10-K"]\nfiscal_year_min=2020\ntickers=["AAPL","ZZZZ"]\n')
    )
    with pytest.raises(UniverseError, match="ZZZZ"):
        resolve_ciks(u, ticker_map())


def test_tickers_compared_uppercase_and_ciks_merged(tmp_path: Path) -> None:
    u = load_universe(
        write(
            tmp_path,
            'forms=["10-K"]\nfiscal_year_min=2020\ntickers=["aapl"]\nciks=[34088, 320193, 999]\n',
        )
    )
    resolved = resolve_ciks(u, ticker_map())
    assert list(resolved) == [320193, 34088, 999]
    assert resolved[320193].ticker == "AAPL"
    assert resolved[34088].ticker == "XOM"  # explicit CIK known to the map
    assert resolved[999].ticker == ""


def test_store_raw_false_accepted_by_loader(tmp_path: Path) -> None:
    u = load_universe(
        write(tmp_path, 'forms=["10-K"]\nfiscal_year_min=2020\nstore_raw=false\nciks=[1]\n')
    )
    assert u.store_raw is False


def test_missing_file_and_missing_key(tmp_path: Path) -> None:
    with pytest.raises(UniverseError):
        load_universe(str(tmp_path / "nope.toml"))
    with pytest.raises(UniverseError, match="fiscal_year_min"):
        load_universe(write(tmp_path, 'forms=["10-K"]\nciks=[1]\n'))


def test_normalise_company_name() -> None:
    assert normalise_company_name("The Coca-Cola Company") == "COCA COLA"
    assert normalise_company_name("Apple Inc.") == "APPLE"
    assert normalise_company_name("3M Co") == "3M"
    assert normalise_company_name("Johnson & Johnson") == "JOHNSON JOHNSON"
    assert normalise_company_name("AES Corporation") == "AES"


def test_match_company_names() -> None:
    tm = ticker_map()
    matches = {m.name: m for m in match_company_names(["Apple Inc", "Exxon Mobil", "Boeing"], tm)}
    assert matches["Apple Inc"].entry is not None
    assert matches["Apple Inc"].entry.ticker == "AAPL"
    # "EXXON MOBIL" vs SEC "EXXON MOBIL CORP": exact after normalisation.
    assert matches["Exxon Mobil"].entry is not None
    assert matches["Boeing"].entry is not None
    assert matches["Boeing"].entry.ticker == "BA"


def test_match_unresolved_and_ambiguous() -> None:
    tm = {
        "GOOGL": TickerEntry(1652044, "GOOGL", "Alphabet Inc."),
        "GOOG": TickerEntry(1652044, "GOOG", "Alphabet Inc."),
        "AA": TickerEntry(1, "AA", "Acme Corp"),
        "AB": TickerEntry(2, "AB", "Acme Inc"),
    }
    by_name = {m.name: m for m in match_company_names(["Alphabet", "Acme", "Costco Wholesale"], tm)}
    assert by_name["Alphabet"].entry is not None
    assert by_name["Alphabet"].entry.ticker == "GOOGL"  # same CIK: first ticker
    assert by_name["Acme"].entry is None
    assert "ambiguous" in by_name["Acme"].reason
    assert by_name["Costco Wholesale"].entry is None


def test_render_draft() -> None:
    tm = ticker_map()
    text = render_draft(
        match_company_names(["Apple Inc", "Mystery Corp"], tm), ["XOM", "AAPL", "NOPE"], tm
    )
    assert '"AAPL",  # FinanceBench: Apple Inc -> SEC: Apple Inc.' in text
    assert '"XOM",  # holdings' in text
    assert text.count('"AAPL"') == 1
    assert "#   Mystery Corp" in text
    assert "#   holdings ticker NOPE" in text
    assert "fiscal_year_min = 2014" in text
