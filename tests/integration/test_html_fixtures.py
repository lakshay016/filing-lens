"""Fixture-filing tests for ``extract_blocks`` (task 1.3). No network, no database."""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter

import pytest

from filinglens.parse.html import Block, extract_blocks
from tests.fixtures.filings.load import load_fixture
from tests.snapshot import assert_snapshot

NAMES = ["aapl-fy2022", "aapl-fy2023", "xom-fy2022", "xom-fy2023"]
_PAGE_NUMBER_RE = re.compile(r"^(page\s+)?\d{1,3}(\s+of\s+\d+)?$|^[A-Z]-\d{1,3}$", re.IGNORECASE)


def _summary(blocks: list[Block]) -> dict[str, object]:
    headings = [b for b in blocks if b.kind == "heading"]
    tables = [b for b in blocks if b.kind == "table"]
    digest = hashlib.sha1("".join(b.text for b in blocks).encode("utf-8")).hexdigest()
    return {
        "blocks_by_kind": dict(sorted(Counter(b.kind for b in blocks).items())),
        "headings_by_level": {
            str(k): v for k, v in sorted(Counter(b.level for b in headings).items())
        },
        "total_chars": sum(len(b.text) for b in blocks),
        "first_60_headings": [[b.level, b.text] for b in headings[:60]],
        "first_15_tables": [
            [t.caption, t.text.split("\n")[0], t.text.count("\n") + 1] for t in tables[:15]
        ],
        "sha1_of_block_texts": digest,
    }


@pytest.mark.parametrize("name", NAMES)
def test_fixture_extraction(name: str) -> None:
    document = load_fixture(name)
    start = time.perf_counter()
    blocks = extract_blocks(document)
    elapsed = time.perf_counter() - start
    assert elapsed < 20

    assert extract_blocks(document) == blocks  # deterministic

    tables = [b for b in blocks if b.kind == "table"]
    assert len(tables) >= 20
    assert any(t.caption for t in tables)
    assert any(
        b.kind == "heading" and b.level == 1 and re.match(r"item\s+1a\b", b.text, re.IGNORECASE)
        for b in blocks
    )
    for b in blocks:
        assert "display:none" not in b.text.lower().replace(" ", "")
        assert not b.text.startswith("<")
        if b.kind == "text":
            assert not _PAGE_NUMBER_RE.match(b.text)

    assert_snapshot(f"html_{name}", _summary(blocks))


@pytest.mark.parametrize("name", ["xom-fy2022", "xom-fy2023"])
def test_exxon_item_headings(name: str) -> None:
    # The brief expected a combined "Items 1 and 2" heading; these two Exxon filings
    # (FY2022, FY2023) use separate Item 1 and Item 2 headings instead.
    blocks = extract_blocks(load_fixture(name))
    levels = {
        m.group(1).lower()
        for b in blocks
        if b.kind == "heading" and b.level == 1
        for m in [re.match(r"items?\s+(\d+[abc]?)\b", b.text, re.IGNORECASE)]
        if m
    }
    assert {"1", "2", "1a", "7", "8"} <= levels
