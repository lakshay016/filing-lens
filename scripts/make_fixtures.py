"""Download the four parser fixture filings (task 1.3) and store them zstd-compressed.

Run once, with the repository root as working directory so ``.env`` is found:

    uv run python scripts/make_fixtures.py [--out tests/fixtures/filings]

Prints accession, primary document, sizes and SHA-256 for the fixture README. The
User-Agent is read through settings and never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from pathlib import Path

import zstandard

from filinglens.edgar.client import EdgarClient
from filinglens.edgar.index import document_url, fetch_filing_list

COMPANIES = {"aapl": 320193, "xom": 34088}
YEARS = (2022, 2023)
MAX_COMPRESSED = 1_500_000


async def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    async with EdgarClient() as client:
        for prefix, cik in COMPANIES.items():
            _, filings = await fetch_filing_list(client, cik)
            for year in YEARS:
                matches = [f for f in filings if f.form == "10-K" and f.fiscal_year == year]
                if len(matches) != 1:
                    raise SystemExit(f"{prefix} FY{year}: expected 1 10-K, found {len(matches)}")
                meta = matches[0]
                raw = await client.get_bytes(
                    document_url(cik, meta.accession, meta.primary_document)
                )
                packed = zstandard.ZstdCompressor(level=19).compress(raw)
                path = out / f"{prefix}-fy{year}.htm.zst"
                path.write_bytes(packed)
                print(
                    f"{path.name} | {meta.accession} | {meta.primary_document} | "
                    f"period {meta.period_of_report} | raw {len(raw)} B | "
                    f"sha256 {hashlib.sha256(raw).hexdigest()} | zst {len(packed)} B"
                )
                if len(packed) > MAX_COMPRESSED:
                    raise SystemExit(f"{path.name} exceeds 1.5 MB compressed; stopping")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/filings"))
    args = parser.parse_args()
    asyncio.run(main(args.out))
