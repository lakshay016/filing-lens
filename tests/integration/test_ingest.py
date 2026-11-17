from __future__ import annotations

import json
import random
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from filinglens.db.models import Company, Filing
from filinglens.edgar.client import EdgarClient
from filinglens.edgar.fetch import IngestSummary, ingest
from filinglens.edgar.index import document_url
from filinglens.edgar.store import raw_path, read_raw
from filinglens.edgar.universe import Universe

pytestmark = pytest.mark.db

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "edgar"
UA = "Test Name test@example.com"
AAPL, XOM = 320193, 34088

XOM_SUBMISSIONS: dict[str, Any] = {
    "cik": "34088",
    "name": "EXXON MOBIL CORP",
    "sic": "2911",
    "tickers": ["XOM"],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000034088-24-000010",
                "0000034088-24-000020",
                "0000034088-23-000009",
            ],
            "filingDate": ["2024-02-21", "2024-06-01", "2023-02-22"],
            "reportDate": ["2023-12-31", "2023-12-31", "2022-12-31"],
            "acceptanceDateTime": [
                "2024-02-21T21:30:00.000Z",
                "2024-06-01T12:00:00.000Z",
                "2023-02-22T21:00:00.000Z",
            ],
            "form": ["10-K", "10-K/A", "10-K"],
            "primaryDocument": ["xom-20231231.htm", "xom-20231231a.htm", "xom-20221231.htm"],
        },
        "files": [],
    },
}


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def make_client(ft: FakeTime) -> EdgarClient:
    return EdgarClient(UA, clock=ft.clock, sleep=ft.sleep, rng=random.Random(1))


@pytest.fixture
def factory(db_engine: Engine) -> Iterator[sessionmaker[Session]]:
    def clean() -> None:
        with db_engine.begin() as conn:
            conn.execute(sa.delete(Filing))
            conn.execute(sa.delete(Company))

    clean()
    yield sessionmaker(db_engine, expire_on_commit=False)
    clean()


def universe(**kw: Any) -> Universe:
    base: dict[str, Any] = {
        "name": "test",
        "forms": ("10-K", "10-K405"),
        "fiscal_year_min": 2020,
        "fiscal_year_max": None,
        "store_raw": True,
        "tickers": ("AAPL", "XOM"),
        "ciks": (),
    }
    base.update(kw)
    return Universe(**base)


class Mocks:
    """respx routes for tickers, both submissions files, and one route per document."""

    def __init__(self, router: respx.MockRouter) -> None:
        self.router = router
        tickers = (FIX / "company_tickers.json").read_bytes()
        router.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, content=tickers)
        )
        main = json.loads((FIX / "submissions_main.json").read_text())
        router.get(f"https://data.sec.gov/submissions/CIK{AAPL:010d}.json").mock(
            return_value=httpx.Response(200, json=main)
        )
        router.get("https://data.sec.gov/submissions/CIK0000320193-submissions-001.json").mock(
            return_value=httpx.Response(200, content=(FIX / "submissions_page.json").read_bytes())
        )
        router.get(f"https://data.sec.gov/submissions/CIK{XOM:010d}.json").mock(
            return_value=httpx.Response(200, json=XOM_SUBMISSIONS)
        )
        self.docs: dict[str, respx.Route] = {}
        for cik, payload in ((AAPL, main), (XOM, XOM_SUBMISSIONS)):
            recent = payload["filings"]["recent"]
            for acc, doc in zip(recent["accessionNumber"], recent["primaryDocument"], strict=True):
                if not doc:
                    continue
                url = document_url(cik, acc, doc)
                body = f"<html>{acc}</html>".encode() * 50
                self.docs[acc] = router.get(url).mock(
                    return_value=httpx.Response(200, content=body)
                )

    def doc_calls(self) -> int:
        return sum(r.call_count for r in self.docs.values())


@pytest.fixture
def mocks() -> Iterator[Mocks]:
    with respx.mock(assert_all_called=False) as router:
        yield Mocks(router)


async def run(
    factory: sessionmaker[Session], tmp_path: Path, uni: Universe | None = None, **kw: Any
) -> IngestSummary:
    async with make_client(FakeTime()) as client:
        return await ingest(uni or universe(), factory, client, data_dir=tmp_path, **kw)


def statuses(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory() as s:
        return {a: st for a, st in s.execute(sa.select(Filing.accession, Filing.fetch_status))}


async def test_first_and_second_run(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    first = await run(factory, tmp_path)
    # AAPL in range (2020+): 10-K 2024, 2023, 2022, 2021, 2020 + the 2023 10-K/A.
    # XOM: two 10-Ks and one 10-K/A.
    assert first.companies == 2
    assert first.filings_new == 9
    assert first.fetched == 7
    assert first.skipped == 2  # the two amendments
    assert first.failed == 0
    assert first.bytes > 0
    st = statuses(factory)
    assert st["0000320193-23-000108"] == "skipped"
    assert st["0000034088-24-000020"] == "skipped"
    assert sum(1 for v in st.values() if v == "ok") == 7
    assert mocks.docs["0000320193-23-000108"].call_count == 0
    assert mocks.docs["0000034088-24-000020"].call_count == 0
    assert mocks.doc_calls() == 7
    # raw file is on disk and decodes
    p = raw_path(tmp_path, AAPL, "0000320193-24-000123", "aapl-20240928.htm")
    assert read_raw(p).startswith(b"<html>0000320193-24-000123")
    # the 2019 filing (no reportDate) and the pre-2020 page are not in the manifest
    assert "0000320193-19-000119" not in st
    assert "0001193125-17-323525" not in st

    second = await run(factory, tmp_path)
    assert second.fetched == 0
    assert second.filings_new == 0
    assert second.skipped == 9
    assert second.failed == 0
    assert mocks.doc_calls() == 7  # no further document requests


async def test_accepted_at_is_utc(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    await run(factory, tmp_path)
    with factory() as s:
        row = s.execute(
            sa.select(Filing.accepted_at).where(Filing.accession == "0000320193-23-000106")
        ).scalar_one()
    assert row == datetime(2023, 11, 2, 22, 8, 27, tzinfo=UTC)
    assert row.utcoffset().total_seconds() == 0


async def test_company_row(factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks) -> None:
    await run(factory, tmp_path)
    with factory() as s:
        c = s.get(Company, XOM)
    assert c is not None
    assert (c.name, c.ticker, c.sic, c.sector) == (
        "EXXON MOBIL CORP",
        "XOM",
        "2911",
        "Manufacturing",
    )


async def test_404_fails_then_retried(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    bad = mocks.docs["0000034088-23-000009"]
    bad.mock(return_value=httpx.Response(404))
    first = await run(factory, tmp_path)
    assert first.failed == 1
    assert first.fetched == 6
    assert statuses(factory)["0000034088-23-000009"] == "failed"
    with factory() as s:
        err = s.execute(
            sa.select(Filing.fetch_error).where(Filing.accession == "0000034088-23-000009")
        ).scalar_one()
    assert err == "status 404 after 1 attempt(s)"

    bad.mock(return_value=httpx.Response(200, content=b"<html>fixed</html>"))
    second = await run(factory, tmp_path)
    assert second.fetched == 1
    assert second.failed == 0
    st = statuses(factory)
    assert st["0000034088-23-000009"] == "ok"
    with factory() as s:
        err = s.execute(
            sa.select(Filing.fetch_error).where(Filing.accession == "0000034088-23-000009")
        ).scalar_one()
    assert err is None


async def test_limit_takes_newest(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    first = await run(factory, tmp_path, limit=1)
    assert first.fetched == 1
    assert mocks.doc_calls() == 1
    # newest 10-K by filed_date among both companies is AAPL 2024-11-01
    assert mocks.docs["0000320193-24-000123"].call_count == 1
    assert sum(1 for v in statuses(factory).values() if v == "ok") == 1


async def test_deleted_raw_file_is_fetched_again(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    await run(factory, tmp_path)
    p = raw_path(tmp_path, AAPL, "0000320193-22-000108", "aapl-20220924.htm")
    p.unlink()
    again = await run(factory, tmp_path)
    assert again.fetched == 1
    assert mocks.docs["0000320193-22-000108"].call_count == 2
    assert p.exists()


async def test_year_range_and_since(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    summary = await run(factory, tmp_path, universe(fiscal_year_min=2018), since=2023)
    # AAPL 2024, 2023 (+ 10-K/A), XOM 2023 (10-K 2024-02 is FY2023) and its 10-K/A; XOM FY2022 out.
    assert summary.fetched == 3
    assert "0000034088-23-000009" not in statuses(factory)


async def test_text_only_mode_not_implemented(
    factory: sessionmaker[Session], tmp_path: Path, mocks: Mocks
) -> None:
    with pytest.raises(NotImplementedError, match=r"task 3\.2"):
        await run(factory, tmp_path, universe(store_raw=False))
