"""Paragraph storage in the parse pipeline, against the local test database (task 1.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from filinglens.db.models import AlignmentEdge, AlignmentPair, Filing, Paragraph
from filinglens.parse.pipeline import build_report, parse_filing, parse_universe
from tests.fixtures.filings.load import load_fixture
from tests.integration.test_parse_pipeline import CIK, add_filing, factory  # noqa: F401

pytestmark = pytest.mark.db


def count_paragraphs(session: Session, filing: Filing) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(Paragraph).where(Paragraph.filing_id == filing.id)
        )
        or 0
    )


def test_parse_filing_stores_paragraphs(db_session: Session, tmp_path: Path) -> None:
    filing = add_filing(db_session, tmp_path, "0000000000-23-000101", load_fixture("aapl-fy2023"))
    parse_filing(db_session, filing, tmp_path)
    db_session.flush()
    rows = list(
        db_session.scalars(
            select(Paragraph).where(Paragraph.filing_id == filing.id).order_by(Paragraph.seq)
        )
    )
    assert filing.parse_status == "ok" and len(rows) > 300
    assert [r.seq for r in rows] == list(range(len(rows)))
    assert {"front", "1", "1A", "7", "8"} <= {r.item for r in rows}
    first_1a = next(r for r in rows if r.item == "1A")
    assert first_1a.text and len(first_1a.exact_hash) == len(first_1a.masked_hash) == 40
    assert first_1a.n_tokens > 0 and first_1a.is_table is False
    assert any(r.heading_path for r in rows if r.item == "1A")
    assert any(r.is_table for r in rows)


def make_pair_row(session: Session, old: Filing, new: Filing) -> int:
    pair = AlignmentPair(
        cik=CIK,
        old_filing_id=old.id,
        new_filing_id=new.id,
        item="1A",
        eligible=True,
        aligner_version="0",
    )
    session.add(pair)
    session.flush()
    session.add(AlignmentEdge(pair_id=pair.id, label="added"))
    session.flush()
    return pair.id


def test_reparse_replaces_paragraphs_and_alignments(db_session: Session, tmp_path: Path) -> None:
    old = add_filing(db_session, tmp_path, "0000000000-22-000102", load_fixture("aapl-fy2022"))
    new = add_filing(db_session, tmp_path, "0000000000-23-000103", load_fixture("aapl-fy2023"))
    other = add_filing(db_session, tmp_path, "0000000000-23-000104", load_fixture("aapl-fy2023"))
    parse_filing(db_session, new, tmp_path)
    db_session.flush()
    n_first = count_paragraphs(db_session, new)
    first_ids = set(db_session.scalars(select(Paragraph.id).where(Paragraph.filing_id == new.id)))

    stale_new = make_pair_row(db_session, old, new)  # `new` is the new side
    stale_old = make_pair_row(db_session, new, old)  # `new` is the old side
    unrelated = make_pair_row(db_session, old, other)

    parse_filing(db_session, new, tmp_path)  # what `--force` does
    db_session.flush()
    assert count_paragraphs(db_session, new) == n_first  # no duplicates
    second_ids = set(db_session.scalars(select(Paragraph.id).where(Paragraph.filing_id == new.id)))
    assert not first_ids & second_ids  # replaced, not kept
    remaining = set(db_session.scalars(select(AlignmentPair.id)))
    assert stale_new not in remaining and stale_old not in remaining
    assert unrelated in remaining
    assert db_session.scalar(select(func.count()).select_from(AlignmentEdge)) == 1


def test_failed_filing_stores_none_and_clears_old_rows(db_session: Session, tmp_path: Path) -> None:
    filing = add_filing(db_session, tmp_path, "0000000000-23-000105", load_fixture("aapl-fy2023"))
    parse_filing(db_session, filing, tmp_path)
    db_session.flush()
    assert count_paragraphs(db_session, filing) > 0

    # the raw file is now not HTML: the re-parse fails and must not leave stale paragraphs
    broken = add_filing(db_session, tmp_path, "0000000000-23-000106", b"plain text only\n" * 50)
    assert parse_filing(db_session, broken, tmp_path) is None
    assert broken.parse_status == "failed" and count_paragraphs(db_session, broken) == 0

    missing = add_filing(db_session, tmp_path, "0000000000-23-000107", None)
    parse_filing(db_session, missing, tmp_path)
    assert missing.parse_status == "failed" and count_paragraphs(db_session, missing) == 0


def test_failed_reparse_removes_previous_paragraphs(db_session: Session, tmp_path: Path) -> None:
    from filinglens.edgar.store import raw_path, write_raw

    filing = add_filing(db_session, tmp_path, "0000000000-23-000108", load_fixture("aapl-fy2023"))
    parse_filing(db_session, filing, tmp_path)
    db_session.flush()
    assert count_paragraphs(db_session, filing) > 0
    write_raw(raw_path(tmp_path, CIK, filing.accession, "doc.htm"), b"plain text only\n" * 50)
    parse_filing(db_session, filing, tmp_path)
    db_session.flush()
    assert filing.parse_status == "failed" and count_paragraphs(db_session, filing) == 0


def test_report_line(
    db_session: Session,
    factory: sessionmaker[Session],  # noqa: F811
    tmp_path: Path,
) -> None:
    add_filing(db_session, tmp_path, "0000000000-23-000109", load_fixture("aapl-fy2023"))
    add_filing(db_session, tmp_path, "0000000000-23-000110", load_fixture("aapl-fy2022"))
    add_filing(db_session, tmp_path, "0000000000-23-000111", b"plain text\n" * 100)
    parse_universe(factory, [CIK], tmp_path)
    total = db_session.scalar(select(func.count()).select_from(Paragraph)) or 0
    line = next(
        row for row in build_report(db_session, [CIK]).splitlines() if row.startswith("paragraphs")
    )
    assert f"paragraphs stored: {total} in 2 ok/partial filings, median " in line
