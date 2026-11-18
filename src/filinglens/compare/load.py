"""Load filings and Item paragraphs for the baseline comparison."""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from filinglens.db.models import Company, Filing, Paragraph
from filinglens.edgar.index import document_url
from filinglens.edgar.universe import Universe
from filinglens.parse.items import item_status


@dataclass(frozen=True, slots=True)
class FilingRef:
    filing_id: int
    cik: int
    company: str
    accession: str
    fiscal_year: int
    period_of_report: date
    filed_date: date
    accepted_at: datetime | None
    url: str
    form: str = "10-K"


@dataclass(frozen=True, slots=True)
class Para:
    seq: int
    n: int  # 1-based position within the Item
    heading_path: tuple[str, ...]
    text: str
    is_table: bool


def filings_for(
    session: Session, universe: Universe, ciks: list[int] | None = None
) -> list[FilingRef]:
    """Original filings of the universe's forms that were fetched and parsed.

    One per (company, fiscal year): the earliest ``accepted_at`` wins. Sorted by company
    then period of report. ``ciks`` restricts the companies (the CLI passes the resolved
    CIKs of the universe); when None, every company in the database is considered.
    """
    query = (
        sa.select(Filing, Company.name)
        .join(Company, Company.cik == Filing.cik)
        .where(
            Filing.form.in_(universe.forms),
            Filing.fetch_status == "ok",
            Filing.parse_status.in_(("ok", "partial")),
            Filing.fiscal_year.is_not(None),
            Filing.period_of_report.is_not(None),
            Filing.fiscal_year >= universe.fiscal_year_min,
        )
    )
    if universe.fiscal_year_max is not None:
        query = query.where(Filing.fiscal_year <= universe.fiscal_year_max)
    if ciks is not None:
        query = query.where(Filing.cik.in_(ciks))
    best: dict[tuple[int, int], tuple[Filing, str]] = {}
    for filing, company in session.execute(query):
        assert filing.fiscal_year is not None
        key = (filing.cik, filing.fiscal_year)
        held = best.get(key)
        if held is None or _acceptance_key(filing) < _acceptance_key(held[0]):
            best[key] = (filing, company)
    refs: list[FilingRef] = []
    for filing, company in best.values():
        assert filing.fiscal_year is not None and filing.period_of_report is not None
        refs.append(
            FilingRef(
                filing_id=filing.id,
                cik=filing.cik,
                company=company,
                accession=filing.accession,
                fiscal_year=filing.fiscal_year,
                period_of_report=filing.period_of_report,
                filed_date=filing.filed_date,
                accepted_at=filing.accepted_at,
                url=document_url(filing.cik, filing.accession, filing.primary_document),
                form=filing.form,
            )
        )
    refs.sort(key=lambda r: (r.cik, r.period_of_report, r.accession))
    return refs


ORIGINAL_FORMS = frozenset({"10-K", "10-K405"})
MIN_PERIOD_DAYS = 270  # SPEC 6.1: 9 to 15 months between periods of report
MAX_PERIOD_DAYS = 460


@dataclass(frozen=True, slots=True)
class Gap:
    """Two consecutive filings that SPEC 6.1 does not allow to be compared."""

    old: FilingRef
    new: FilingRef
    reason: str


def plan_pairs(filings: Sequence[FilingRef]) -> list[tuple[FilingRef, FilingRef] | Gap]:
    """Consecutive filings as comparable pairs, or a Gap with the reason (SPEC 6.1).

    ``filings`` are sorted by period of report. A pair needs the same CIK, original 10-K
    forms on both sides and periods 270 to 460 days apart.
    """
    out: list[tuple[FilingRef, FilingRef] | Gap] = []
    for old, new in itertools.pairwise(filings):
        days = (new.period_of_report - old.period_of_report).days
        if old.cik != new.cik:
            out.append(Gap(old, new, f"different companies (CIK {old.cik} and {new.cik})"))
        elif old.form not in ORIGINAL_FORMS or new.form not in ORIGINAL_FORMS:
            out.append(Gap(old, new, f"not both original 10-Ks (forms {old.form} and {new.form})"))
        elif days > MAX_PERIOD_DAYS:
            missing = [f"FY{y}" for y in range(old.fiscal_year + 1, new.fiscal_year)]
            tail = f"; {', '.join(missing)} filing missing" if missing else ""
            out.append(Gap(old, new, f"period gap {days} days{tail}"))
        elif days < MIN_PERIOD_DAYS:
            out.append(Gap(old, new, f"period gap {days} days; periods too close together"))
        else:
            out.append((old, new))
    return out


def _acceptance_key(filing: Filing) -> tuple[bool, float, str]:
    # a missing acceptance time sorts after any real one
    return (
        filing.accepted_at is None,
        filing.accepted_at.timestamp() if filing.accepted_at else 0.0,
        filing.accession,
    )


def item_paragraphs(session: Session, filing_id: int, item: str) -> list[Para] | None:
    """Paragraphs of ``item`` in order, or None when the Item's status is not ok."""
    notes = session.scalar(sa.select(Filing.parse_notes).where(Filing.id == filing_id))
    if notes is None or item_status(notes, item) != "ok":
        return None
    rows = session.execute(
        sa.select(Paragraph.seq, Paragraph.heading_path, Paragraph.text, Paragraph.is_table)
        .where(Paragraph.filing_id == filing_id, Paragraph.item == item)
        .order_by(Paragraph.seq)
    ).all()
    return [
        Para(seq=r.seq, n=i, heading_path=tuple(r.heading_path), text=r.text, is_table=r.is_table)
        for i, r in enumerate(rows, start=1)
    ]
