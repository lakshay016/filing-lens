"""Parse stored filings: raw file to blocks to Item segmentation (brief 1.4)."""

from __future__ import annotations

import logging
import traceback
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from filinglens.db.models import Company, Filing
from filinglens.edgar.store import raw_path, read_raw
from filinglens.parse.html import NotHtmlError, extract_blocks
from filinglens.parse.items import Segmentation, segment
from filinglens.versions import PARSER_VERSION

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, slots=True)
class ParseSummary:
    selected: int
    ok: int
    partial: int
    failed: int


def _fail(filing: Filing, reason: str) -> None:
    filing.parse_status = "failed"
    filing.parse_notes = {"status_reasons": [reason], "items": {}, "combined": {}}
    filing.parser_version = PARSER_VERSION


def parse_filing(session: Session, filing: Filing, data_dir: Path) -> Segmentation | None:
    """Parse one filing and set ``parse_status``, ``parse_notes`` and ``parser_version``.

    Returns the segmentation, or None when the filing failed before one existed. Never
    raises for a bad filing. Does not commit; the caller owns the transaction.
    """
    try:
        path = raw_path(data_dir, filing.cik, filing.accession, filing.primary_document)
        blocks = extract_blocks(read_raw(path))
        segmentation = segment(blocks, filing.period_of_report)
    except NotHtmlError:
        _fail(filing, "not_html")
        return None
    except Exception as exc:
        logger.error("parse failed for %s:\n%s", filing.accession, traceback.format_exc())
        _fail(filing, f"error:{type(exc).__name__}")
        return None
    filing.parse_status = segmentation.status
    filing.parse_notes = segmentation.notes
    filing.parser_version = PARSER_VERSION
    # HOOK (task 1.5): normalise blocks and store paragraphs for each section here,
    # inside this transaction, replacing the filing's previous paragraphs.
    return segmentation


def parse_universe(
    session_factory: SessionFactory,
    ciks: Sequence[int],
    data_dir: Path,
    *,
    force: bool = False,
    limit: int | None = None,
) -> ParseSummary:
    query = (
        sa.select(Filing.id)
        .where(Filing.cik.in_(list(ciks)), Filing.fetch_status == "ok")
        .order_by(Filing.cik, Filing.fiscal_year, Filing.id)
    )
    if not force:
        query = query.where(Filing.parser_version.is_distinct_from(PARSER_VERSION))
    if limit is not None:
        query = query.limit(limit)
    with session_factory() as session:
        ids = list(session.scalars(query))

    counts: Counter[str] = Counter()
    for filing_id in ids:
        with session_factory() as session, session.begin():  # one transaction per filing
            filing = session.get(Filing, filing_id)
            if filing is None:
                continue
            parse_filing(session, filing, data_dir)
            counts[filing.parse_status or "failed"] += 1
    return ParseSummary(len(ids), counts["ok"], counts["partial"], counts["failed"])


def _reasons(notes: Any) -> list[str]:
    return list((notes or {}).get("status_reasons", []))


def build_report(session: Session, ciks: Sequence[int]) -> str:
    """Status table by fiscal year, reason counts, and every non-ok filing."""
    rows = session.execute(
        sa.select(
            Filing.accession,
            Filing.fiscal_year,
            Filing.parse_status,
            Filing.parse_notes,
            Company.name,
        )
        .join(Company, Company.cik == Filing.cik)
        .where(Filing.cik.in_(list(ciks)), Filing.fetch_status == "ok")
        .order_by(Filing.fiscal_year, Filing.accession)
    ).all()
    parsed = [r for r in rows if r.parse_status is not None]
    unparsed = len(rows) - len(parsed)

    by_year: dict[int | None, Counter[str]] = defaultdict(Counter)
    for r in parsed:
        by_year[r.fiscal_year][r.parse_status] += 1

    def line(label: str, c: Counter[str]) -> str:
        n = sum(c.values())
        pct = 100 * c["ok"] / n if n else 0.0
        return f"{label:<12}{n:>8}{c['ok']:>8}{c['partial']:>9}{c['failed']:>8}{pct:>8.1f}%"

    out = [f"{'fiscal year':<12}{'filings':>8}{'ok':>8}{'partial':>9}{'failed':>8}{'% ok':>9}"]
    total: Counter[str] = Counter()
    for year in sorted(by_year, key=lambda y: (y is None, y or 0)):
        out.append(line("?" if year is None else str(year), by_year[year]))
        total.update(by_year[year])
    out.append(line("total", total))
    if unparsed:
        out.append(f"({unparsed} fetched filings not parsed yet)")

    bad = [r for r in parsed if r.parse_status != "ok"]
    reason_counts = Counter(x for r in bad for x in _reasons(r.parse_notes))
    if reason_counts:
        out += ["", "status reasons"]
        out += [f"  {n:>4}  {reason}" for reason, n in reason_counts.most_common()]
    if bad:
        out += ["", "non-ok filings"]
        for r in bad:
            out.append(
                f"  {r.accession}  {r.name}  FY{r.fiscal_year}  {r.parse_status}  "
                + ", ".join(_reasons(r.parse_notes))
            )
    return "\n".join(out)
