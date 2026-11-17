"""Parse pipeline against the local test database (task 1.4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from filinglens.db.models import Company, Filing
from filinglens.edgar.store import raw_path, write_raw
from filinglens.parse.pipeline import build_report, parse_filing, parse_universe
from filinglens.versions import PARSER_VERSION
from tests.fixtures.filings.load import load_fixture

pytestmark = pytest.mark.db

CIK = 320193


@pytest.fixture
def factory(db_session: Session) -> sessionmaker[Session]:
    """Sessions that share the test's connection and roll back with it."""
    return sessionmaker(
        bind=db_session.get_bind(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


def add_filing(
    session: Session, data_dir: Path, accession: str, content: bytes | None, **kw: object
) -> Filing:
    if session.get(Company, CIK) is None:
        session.add(Company(cik=CIK, name="Apple Inc."))
    filing = Filing(
        cik=CIK,
        accession=accession,
        form="10-K",
        period_of_report=date(2023, 9, 30),
        fiscal_year=2023,
        filed_date=date(2023, 11, 3),
        primary_document="doc.htm",
        fetch_status="ok",
    )
    for key, value in kw.items():
        setattr(filing, key, value)
    session.add(filing)
    if content is not None:
        write_raw(raw_path(data_dir, CIK, accession, "doc.htm"), content)
    session.commit()
    return filing


def test_parse_filing_sets_status_notes_version(db_session: Session, tmp_path: Path) -> None:
    filing = add_filing(db_session, tmp_path, "0000000000-23-000001", load_fixture("aapl-fy2023"))
    seg = parse_filing(db_session, filing, tmp_path)
    assert seg is not None and seg.status == "ok"
    assert filing.parse_status == "ok"
    assert filing.parser_version == PARSER_VERSION == "2"
    assert filing.parse_notes["status_reasons"] == []
    assert filing.parse_notes["items"]["1A"]["chars"] > 20_000
    assert filing.parse_notes["items"]["7"]["heading"].startswith("Item 7.")


def test_not_html_fails_with_reason(db_session: Session, tmp_path: Path) -> None:
    filing = add_filing(db_session, tmp_path, "0000000000-23-000002", b"plain text only\n" * 50)
    assert parse_filing(db_session, filing, tmp_path) is None
    assert filing.parse_status == "failed"
    assert filing.parse_notes["status_reasons"] == ["not_html"]
    assert filing.parser_version == PARSER_VERSION


def test_missing_raw_file_fails_without_raising(db_session: Session, tmp_path: Path) -> None:
    filing = add_filing(db_session, tmp_path, "0000000000-23-000003", None)
    assert parse_filing(db_session, filing, tmp_path) is None
    assert filing.parse_status == "failed"
    assert filing.parse_notes["status_reasons"] == ["error:FileNotFoundError"]


def test_one_bad_filing_does_not_stop_the_run(
    db_session: Session, factory: sessionmaker[Session], tmp_path: Path
) -> None:
    add_filing(db_session, tmp_path, "0000000000-23-000004", None)  # raw file missing
    add_filing(db_session, tmp_path, "0000000000-23-000005", load_fixture("aapl-fy2022"))
    summary = parse_universe(factory, [CIK], tmp_path)
    assert (summary.selected, summary.ok, summary.failed) == (2, 1, 1)
    status = dict(db_session.execute(select(Filing.accession, Filing.parse_status)).all())
    assert status == {"0000000000-23-000004": "failed", "0000000000-23-000005": "ok"}


def test_skip_unchanged_version_and_force(
    db_session: Session, factory: sessionmaker[Session], tmp_path: Path
) -> None:
    add_filing(db_session, tmp_path, "0000000000-23-000006", load_fixture("aapl-fy2023"))
    add_filing(  # not fetched: never selected
        db_session, tmp_path, "0000000000-23-000007", None, fetch_status="pending"
    )
    first = parse_universe(factory, [CIK], tmp_path)
    assert (first.selected, first.ok) == (1, 1)
    assert parse_universe(factory, [CIK], tmp_path).selected == 0  # same parser_version

    forced = parse_universe(factory, [CIK], tmp_path, force=True)
    assert (forced.selected, forced.ok) == (1, 1)

    db_session.expire_all()
    old = db_session.scalars(select(Filing).where(Filing.accession == "0000000000-23-000006")).one()
    old.parser_version = "1"  # an older parser's output is re-parsed without --force
    db_session.commit()
    assert parse_universe(factory, [CIK], tmp_path).selected == 1


def test_limit(db_session: Session, factory: sessionmaker[Session], tmp_path: Path) -> None:
    for n in (8, 9):
        add_filing(db_session, tmp_path, f"0000000000-23-0000{n:02d}", load_fixture("aapl-fy2023"))
    assert parse_universe(factory, [CIK], tmp_path, limit=1).selected == 1


def test_report(db_session: Session, factory: sessionmaker[Session], tmp_path: Path) -> None:
    add_filing(db_session, tmp_path, "0000000000-23-000010", load_fixture("aapl-fy2023"))
    add_filing(db_session, tmp_path, "0000000000-23-000011", b"plain text\n" * 100)
    add_filing(db_session, tmp_path, "0000000000-23-000012", load_fixture("xom-fy2023"))
    add_filing(db_session, tmp_path, "0000000000-23-000013", load_fixture("aapl-fy2022"))
    parse_universe(factory, [CIK], tmp_path, limit=3)
    text = build_report(db_session, [CIK])
    lines = text.splitlines()
    assert lines[0].split() == ["fiscal", "year", "filings", "ok", "partial", "failed", "%", "ok"]
    assert lines[1].split() == ["2023", "3", "1", "1", "1", "33.3%"]
    assert lines[2].split()[:2] == ["total", "3"]
    assert "(1 fetched filings not parsed yet)" in text
    assert "status reasons" in text and "not_html" in text and "short:7" in text
    assert "0000000000-23-000011  Apple Inc.  FY2023  failed  not_html" in text
