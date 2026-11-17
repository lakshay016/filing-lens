"""Manifest and download: ``fl ingest`` (SPEC §5.2)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from filinglens.config import get_settings
from filinglens.db.models import Company, Filing
from filinglens.edgar.client import EdgarClient, EdgarFetchError
from filinglens.edgar.index import (
    FilingMeta,
    document_url,
    fetch_filing_list,
    fetch_ticker_map,
)
from filinglens.edgar.store import raw_path, write_raw
from filinglens.edgar.universe import Universe, resolve_ciks

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, slots=True)
class IngestSummary:
    companies: int
    filings_seen: int
    filings_new: int
    fetched: int
    skipped: int
    failed: int
    bytes: int


def _error_text(exc: EdgarFetchError) -> str:
    what = f"status {exc.status}" if exc.status is not None else "transport error"
    return f"{what} after {exc.attempts} attempt(s)"


def _sync_manifest(
    session: Session, universe: Universe, metas: list[FilingMeta], since: int | None
) -> tuple[int, int]:
    """Upsert filing rows inside the year range. Returns (rows in range, new rows)."""
    lo = max(universe.fiscal_year_min, since or 0)
    hi = universe.fiscal_year_max
    wanted = [
        m
        for m in metas
        if m.fiscal_year is not None and lo <= m.fiscal_year and (hi is None or m.fiscal_year <= hi)
    ]
    if not wanted:
        return 0, 0
    existing = set(
        session.scalars(
            sa.select(Filing.accession).where(Filing.accession.in_([m.accession for m in wanted]))
        )
    )
    for m in wanted:
        fields = {
            "cik": m.cik,
            "form": m.form,
            "period_of_report": m.period_of_report,
            "fiscal_year": m.fiscal_year,
            "filed_date": m.filed_date,
            "accepted_at": m.accepted_at,
            "primary_document": m.primary_document,
        }
        status = "pending" if m.form in universe.forms else "skipped"
        stmt = pg_insert(Filing).values(accession=m.accession, fetch_status=status, **fields)
        # Refresh metadata only: never touch fetch_status, raw_sha256 or the other state.
        session.execute(stmt.on_conflict_do_update(index_elements=[Filing.accession], set_=fields))
    return len(wanted), len([m for m in wanted if m.accession not in existing])


async def ingest(
    universe: Universe,
    session_factory: SessionFactory,
    client: EdgarClient,
    *,
    since: int | None = None,
    limit: int | None = None,
    concurrency: int = 4,
    data_dir: Path | None = None,
) -> IngestSummary:
    if not universe.store_raw:
        raise NotImplementedError("text-only mode is task 3.2")
    data_dir = data_dir if data_dir is not None else get_settings().data_dir

    # 1. Resolve CIKs. The ticker map is only fetched when the universe names tickers.
    if universe.tickers:
        ticker_map = await fetch_ticker_map(client, data_dir / "cache" / "edgar")
    else:
        ticker_map = {}
    ciks = resolve_ciks(universe, ticker_map)

    # 2. Manifest.
    seen = new = 0
    for cik, entry in ciks.items():
        info, metas = await fetch_filing_list(client, cik)
        seen += len(metas)
        ticker = entry.ticker or info.ticker
        with session_factory() as session, session.begin():
            company = pg_insert(Company).values(
                cik=cik, name=info.name, ticker=ticker, sic=info.sic, sector=info.sector
            )
            session.execute(
                company.on_conflict_do_update(
                    index_elements=[Company.cik],
                    set_={
                        "name": info.name,
                        "ticker": ticker,
                        "sic": info.sic,
                        "sector": info.sector,
                    },
                )
            )
            _, n_new = _sync_manifest(session, universe, metas, since)
            new += n_new
        undated = sum(1 for m in metas if m.fiscal_year is None)
        if undated:
            logger.info("CIK %s: %d filing(s) without a report date skipped", cik, undated)

    # 3. Reconcile with the disk, then pick the downloads.
    lo = max(universe.fiscal_year_min, since or 0)
    hi = universe.fiscal_year_max
    in_scope = [
        Filing.cik.in_(list(ciks)),
        Filing.fiscal_year >= lo,
        *([Filing.fiscal_year <= hi] if hi is not None else []),
    ]
    skipped = 0
    with session_factory() as session, session.begin():
        rows = session.execute(
            sa.select(
                Filing.id,
                Filing.cik,
                Filing.accession,
                Filing.primary_document,
                Filing.fetch_status,
            ).where(*in_scope, Filing.fetch_status.in_(("ok", "skipped")))
        ).all()
        for row in rows:
            path = raw_path(data_dir, row.cik, row.accession, row.primary_document)
            if row.fetch_status == "skipped" or path.exists():
                skipped += 1
            else:
                session.execute(
                    sa.update(Filing).where(Filing.id == row.id).values(fetch_status="pending")
                )
        query = (
            sa.select(Filing.id, Filing.cik, Filing.accession, Filing.primary_document)
            .where(
                *in_scope,
                Filing.form.in_(universe.forms),
                Filing.fetch_status.in_(("pending", "failed")),
            )
            .order_by(Filing.filed_date.desc(), Filing.id)
        )
        if limit is not None:
            query = query.limit(limit)
        todo = session.execute(query).all()

    fetched = failed = total_bytes = 0
    queue: asyncio.Queue[tuple[int, int, str, str]] = asyncio.Queue()
    for job in todo:
        queue.put_nowait((job.id, job.cik, job.accession, job.primary_document))

    async def worker() -> None:
        nonlocal fetched, failed, total_bytes
        while True:
            try:
                filing_id, cik, accession, primary = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            url = document_url(cik, accession, primary)
            try:
                content = await client.get_bytes(url)
            except EdgarFetchError as exc:
                failed += 1
                logger.warning("fetch failed for %s: %s", accession, _error_text(exc))
                with session_factory() as session, session.begin():
                    session.execute(
                        sa.update(Filing)
                        .where(Filing.id == filing_id)
                        .values(fetch_status="failed", fetch_error=_error_text(exc))
                    )
                continue
            sha, size = await asyncio.to_thread(
                write_raw, raw_path(data_dir, cik, accession, primary), content
            )
            with session_factory() as session, session.begin():
                session.execute(
                    sa.update(Filing)
                    .where(Filing.id == filing_id)
                    .values(raw_sha256=sha, raw_bytes=size, fetch_status="ok", fetch_error=None)
                )
            fetched += 1
            total_bytes += size

    await asyncio.gather(*(worker() for _ in range(max(1, concurrency))))
    return IngestSummary(
        companies=len(ciks),
        filings_seen=seen,
        filings_new=new,
        fetched=fetched,
        skipped=skipped,
        failed=failed,
        bytes=total_bytes,
    )
