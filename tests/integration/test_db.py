from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from filinglens.config import Settings
from filinglens.db.models import AlignmentEdge, AlignmentPair, Company, Filing, Paragraph

pytestmark = pytest.mark.db

SLICE1_TABLES = {
    "company",
    "filing",
    "paragraph",
    "alignment_pair",
    "alignment_edge",
    "change_label",
    "change_pred",
    "numeric_alert",
    "alert",
}


def _filing(accession: str, year: int) -> Filing:
    return Filing(
        cik=320193,
        accession=accession,
        form="10-K",
        fiscal_year=year,
        filed_date=dt.date(year + 1, 1, 15),
        primary_document="a.htm",
    )


def _two_filings(session: Session) -> tuple[Filing, Filing]:
    session.add(Company(cik=320193, name="Example Inc"))
    old, new = _filing("0000320193-22-000001", 2021), _filing("0000320193-23-000001", 2022)
    session.add_all([old, new])
    session.flush()
    return old, new


def _pair(old: Filing, new: Filing, item: str | None = None) -> AlignmentPair:
    return AlignmentPair(
        cik=320193,
        old_filing_id=old.id,
        new_filing_id=new.id,
        item=item,
        eligible=True,
        aligner_version="t",
    )


def test_tables_exist(db_engine: Engine) -> None:
    names = set(inspect(db_engine).get_table_names())
    assert names >= SLICE1_TABLES
    assert not names & {"chain", "version", "fact", "trace"}


def test_vector_extension(db_session: Session) -> None:
    extnames = db_session.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    assert "vector" in extnames


def test_round_trip(db_session: Session) -> None:
    old, new = _two_filings(db_session)
    p1 = Paragraph(
        filing_id=old.id,
        item="1A",
        seq=0,
        text="hello",
        n_tokens=1,
        exact_hash="a" * 40,
        masked_hash="b" * 40,
    )
    p2 = Paragraph(
        filing_id=new.id,
        item="1A",
        seq=0,
        heading_path=["Risk", "Sub"],
        text="hello!",
        is_table=True,
        n_tokens=1,
        exact_hash="c" * 40,
        masked_hash="b" * 40,
    )
    db_session.add_all([p1, p2])
    pair = _pair(old, new, "1A")
    db_session.add(pair)
    db_session.flush()
    edge = AlignmentEdge(
        pair_id=pair.id, label="modified", old_paragraph_ids=[p1.id], new_paragraph_ids=[p2.id]
    )
    db_session.add(edge)
    db_session.flush()
    db_session.expire_all()

    got = db_session.scalars(select(AlignmentEdge)).one()
    assert got.old_paragraph_ids == [p1.id]
    assert got.new_paragraph_ids == [p2.id]
    assert got.n_ins == 0 and got.changed_ratio == 0 and got.cross_item is False
    assert db_session.get(Paragraph, p2.id).heading_path == ["Risk", "Sub"]  # type: ignore[union-attr]
    assert db_session.get(Paragraph, p1.id).heading_path == []  # type: ignore[union-attr]
    assert db_session.get(Filing, old.id).fetch_status == "pending"  # type: ignore[union-attr]
    assert db_session.get(Filing, old.id).created_at is not None  # type: ignore[union-attr]


def test_fetch_status_check(db_session: Session) -> None:
    db_session.add(Company(cik=320193, name="Example Inc"))
    filing = _filing("0000320193-22-000009", 2021)
    filing.fetch_status = "bogus"
    db_session.add(filing)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_pair_unique_with_null_item(db_session: Session) -> None:
    old, new = _two_filings(db_session)
    db_session.add(_pair(old, new))
    db_session.flush()
    db_session.add(_pair(old, new))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_filing_delete_cascades(db_session: Session) -> None:
    old, new = _two_filings(db_session)
    db_session.add(
        Paragraph(
            filing_id=old.id,
            item="1",
            seq=0,
            text="x",
            n_tokens=1,
            exact_hash="a" * 40,
            masked_hash="a" * 40,
        )
    )
    db_session.add(_pair(old, new))
    db_session.flush()

    db_session.execute(text("DELETE FROM filing WHERE id = :i"), {"i": old.id})
    assert db_session.execute(text("SELECT count(*) FROM paragraph")).scalar_one() == 0
    assert db_session.execute(text("SELECT count(*) FROM alignment_pair")).scalar_one() == 0


def test_test_database_url_name() -> None:
    assert Settings().test_database_url().endswith("/filinglens_test")
