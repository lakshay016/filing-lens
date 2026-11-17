"""Loading filings and Item paragraphs for the comparison, against the test database."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from filinglens.compare.load import filings_for, item_paragraphs
from filinglens.db.models import Company, Filing, Paragraph
from filinglens.edgar.universe import Universe

pytestmark = pytest.mark.db

CIK = 34088
UNIVERSE = Universe(
    name="t",
    forms=("10-K",),
    fiscal_year_min=2021,
    fiscal_year_max=2023,
    store_raw=True,
    tickers=(),
    ciks=(CIK,),
)


def add_filing(
    session: Session,
    accession: str,
    year: int,
    accepted: datetime | None,
    *,
    form: str = "10-K",
    notes: dict[str, object] | None = None,
    status: str = "ok",
) -> Filing:
    if session.get(Company, CIK) is None:
        session.add(Company(cik=CIK, name="Exxon Mobil Corp"))
    filing = Filing(
        cik=CIK,
        accession=accession,
        form=form,
        period_of_report=date(year, 12, 31),
        fiscal_year=year,
        filed_date=date(year + 1, 2, 20),
        accepted_at=accepted,
        primary_document="doc.htm",
        fetch_status="ok",
        parse_status=status,
        parse_notes=notes if notes is not None else {"items": {"1A": {"status": "ok"}}},
    )
    session.add(filing)
    session.flush()
    return filing


def test_one_per_fiscal_year_earliest_accepted_sorted(db_session: Session) -> None:
    late = datetime(2023, 3, 1, tzinfo=UTC)
    early = datetime(2023, 2, 22, tzinfo=UTC)
    add_filing(db_session, "0000034088-24-000018", 2023, datetime(2024, 2, 28, tzinfo=UTC))
    add_filing(db_session, "0000034088-23-000099", 2022, late)
    add_filing(db_session, "0000034088-23-000020", 2022, early)
    add_filing(db_session, "0000034088-22-000011", 2021, datetime(2022, 2, 23, tzinfo=UTC))
    add_filing(db_session, "0000034088-22-000012", 2021, None, form="10-K/A")  # not original
    add_filing(db_session, "0000034088-24-000001", 2023, None, status="failed")
    refs = filings_for(db_session, UNIVERSE, [CIK])
    assert [(r.fiscal_year, r.accession) for r in refs] == [
        (2021, "0000034088-22-000011"),
        (2022, "0000034088-23-000020"),
        (2023, "0000034088-24-000018"),
    ]
    assert refs[0].company == "Exxon Mobil Corp"
    assert refs[0].url == (
        "https://www.sec.gov/Archives/edgar/data/34088/000003408822000011/doc.htm"
    )


def test_item_paragraphs_numbering_and_short_item(db_session: Session) -> None:
    filing = add_filing(
        db_session,
        "0000034088-22-000011",
        2021,
        None,
        notes={"items": {"1A": {"status": "ok"}, "7": {"status": "short"}}},
    )
    for seq, (item, text) in enumerate([("1", "x"), ("1A", "first"), ("1A", "second"), ("7", "y")]):
        db_session.add(
            Paragraph(
                filing_id=filing.id,
                item=item,
                seq=seq,
                heading_path=["H"] if item == "1A" else [],
                text=text,
                is_table=False,
                n_tokens=1,
                exact_hash="0" * 40,
                masked_hash="0" * 40,
            )
        )
    db_session.flush()
    paras = item_paragraphs(db_session, filing.id, "1A")
    assert paras is not None
    assert [(p.seq, p.n, p.text, p.heading_path) for p in paras] == [
        (1, 1, "first", ("H",)),
        (2, 2, "second", ("H",)),
    ]
    assert item_paragraphs(db_session, filing.id, "7") is None
    assert item_paragraphs(db_session, filing.id, "9") is None
