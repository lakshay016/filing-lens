"""Tests for scripts/check_extraction.py on small synthetic filings (no database, no network)."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

from filinglens.parse.html import extract_blocks
from filinglens.parse.items import segment
from filinglens.parse.paragraphs import build_paragraphs

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_extraction.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_extraction", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_extraction"] = module
    spec.loader.exec_module(module)
    return module


ce: Any = _load()

TOPICS = [
    "supply chain disruption",
    "currency exchange rates",
    "cyber security incidents",
    "regulatory scrutiny",
    "customer concentration",
    "commodity price swings",
    "talent retention",
    "litigation exposure",
    "climate related events",
    "data privacy rules",
]


def _para(n: int, topic: str) -> str:
    return (
        f"Risk number {n} concerns {topic}, which could materially and adversely affect the "
        f"Company's results of operations, financial condition and stock price in ways that "
        f"are difficult to predict, and management may not be able to mitigate them in time."
    )


def _filing(footers: bool = False, page_numbers: bool = False) -> bytes:
    body: list[str] = []
    for i, topic in enumerate(TOPICS):
        body.append(f"<p>{_para(i, topic)}</p>")
        if footers and i % 3 == 2:
            body.append("<p>Example Corp | 2022 Annual Report on Form 10-K | 12</p>")
        if page_numbers and i % 3 == 2:
            body.append("<p>12</p>")
    html = (
        "<html><body>"
        "<div style='display:none'>hidden words that must not count</div>"
        "<table><tr><td>Item 1.</td><td>Business</td></tr>"
        "<tr><td>Item 1A.</td><td>Risk Factors 5</td></tr>"
        "<tr><td>Item 1B.</td><td>Unresolved Staff Comments 9</td></tr></table>"
        "<p><b>Item 1. Business</b></p>"
        + "".join(f"<p>{_para(50 + i, 'the business section')}</p>" for i in range(8))
        + "<p><b>Item 1A. Risk Factors</b></p>"
        + "".join(body)
        + "<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p>"
        "<p><b>Item 2. Properties</b></p><p>Headquarters.</p></body></html>"
    )
    return html.encode()


def _stored(
    document: bytes, drop: int | None = None, swap: tuple[int, int] | None = None
) -> list[Any]:
    blocks = extract_blocks(document)
    recs = [r for r in build_paragraphs(blocks, segment(blocks, None)) if r.item == "1A"]
    stored = [ce.StoredParagraph(r.seq, r.text, r.is_table, r.heading_path) for r in recs]
    if drop is not None:
        stored.pop(drop)
    if swap is not None:
        a, b = swap
        first, second = stored[a], stored[b]
        stored[a], stored[b] = replace(first, text=second.text), replace(second, text=first.text)
    return stored


def test_full_coverage_passes() -> None:
    doc = _filing()
    report = ce.analyse(doc, _stored(doc), "1A")
    assert report.heading.passed, report.heading.problems
    assert report.recon.found == report.recon.total == len(TOPICS)
    assert report.recon.stretches == []
    assert report.recon.coverage > 0.99
    assert report.passed
    assert [m.chosen for m in report.heading.mentions].count(True) == 1
    assert len(report.heading.mentions) == 2  # contents row and body heading


def test_hidden_text_is_not_in_the_raw_section() -> None:
    assert "hidden words" not in ce.raw_text(_filing()).text


def test_dropped_paragraph_is_an_unexplained_stretch() -> None:
    doc = _filing()
    report = ce.analyse(doc, _stored(doc, drop=4), "1A")
    assert report.recon.not_found == []
    assert len(report.recon.unexplained) == 1
    assert report.recon.unexplained[0].first_words.startswith("Risk number 4 concerns")
    assert report.recon.coverage < 1
    assert not report.passed


def test_out_of_order_paragraph_fails() -> None:
    doc = _filing()
    report = ce.analyse(doc, _stored(doc, swap=(2, 6)), "1A")
    assert report.recon.not_found
    assert report.recon.not_found[0].reason == "out of order"
    assert not report.passed


def test_footers_are_classified_not_unexplained() -> None:
    doc = _filing(footers=True)
    report = ce.analyse(doc, _stored(doc), "1A")
    assert report.recon.unexplained == []
    assert report.passed


def test_page_number_line_is_classified_not_unexplained() -> None:
    doc = _filing(page_numbers=True)
    blocks = extract_blocks(doc)
    seg = segment(blocks, None)
    section = next(s for s in seg.sections if s.item == "1A")
    rec = ce.reconcile(ce.raw_text(doc), blocks, seg.sections, section, _stored(doc), min_stretch=0)
    assert rec.stretches
    assert all(s.classification == "page number" for s in rec.stretches)
    assert rec.passed


def test_contents_entry_chosen_as_heading_fails() -> None:
    blocks = extract_blocks(_filing())
    seg = segment(blocks, None)
    section = next(s for s in seg.sections if s.item == "1A")
    toc_index = next(
        i
        for i, b in enumerate(blocks)
        if b.text.startswith("Item 1A") and i != section.heading_index
    )
    fake = replace(section, heading_index=toc_index, start=toc_index + 1, chars=30)
    assert not ce.check_heading(blocks, fake, "1A").passed


def _paged_filing() -> bytes:
    """Microsoft shape: a bare "Item 1A" page header after every second risk paragraph."""
    body: list[str] = []
    for i, topic in enumerate(TOPICS):
        if i and i % 2 == 0:
            body.append("<p><b>Item 1A</b></p>")
        body.append(f"<p>{_para(i, topic)}</p>")
    html = (
        "<html><body>"
        "<table><tr><td>Item 1.</td><td>Business</td></tr>"
        "<tr><td>Item 1A.</td><td>Risk Factors 5</td></tr>"
        "<tr><td>Item 1B.</td><td>Unresolved Staff Comments 9</td></tr></table>"
        "<p><b>ITEM 1. BUSINESS</b></p>"
        + "".join(f"<p>{_para(50 + i, 'the business section')}</p>" for i in range(8))
        + "<p><b>ITEM 1A. RISK FACTORS</b></p>"
        + "".join(body)
        + "<p><b>ITEM 1B. UNRESOLVED STAFF COMMENTS</b></p><p>None.</p>"
        "<p><b>ITEM 2. PROPERTIES</b></p><p>Headquarters.</p></body></html>"
    )
    return html.encode()


def test_raw_bounds_start_at_the_body_heading_not_the_contents() -> None:
    raw = ce.raw_text(_paged_filing())
    bounds = ce.raw_bounds(raw, "1A")
    assert not isinstance(bounds, str), bounds
    start, end, _, note, _ = bounds
    assert raw.text[start:].startswith("ITEM 1A. RISK FACTORS")
    assert raw.text[end:].startswith("ITEM 1B. UNRESOLVED STAFF COMMENTS")
    assert "occurrence 2 of 6" in note  # contents row, body heading, 4 page headers


def test_repeated_item_headers_are_classified() -> None:
    doc = _paged_filing()
    blocks = extract_blocks(doc)
    seg = segment(blocks, None)
    section = next(s for s in seg.sections if s.item == "1A")
    assert blocks[section.heading_index or 0].text == "ITEM 1A. RISK FACTORS"
    rec = ce.reconcile(ce.raw_text(doc), blocks, seg.sections, section, _stored(doc), 0)
    assert rec.found == rec.total == len(TOPICS)
    assert len(rec.stretches) == 4
    assert all(s.classification == "repeated Item header" for s in rec.stretches)
    assert rec.passed
    assert ce.analyse(doc, _stored(doc), "1A").passed


def test_late_start_at_a_page_header_fails_the_interior_check() -> None:
    # Parser output as before the fix: the section starts at a later "Item 1A" page
    # header, so the paragraphs before it are missing from the stored Item.
    doc = _paged_filing()
    blocks = extract_blocks(doc)
    seg = segment(blocks, None)
    section = next(s for s in seg.sections if s.item == "1A")
    page_headers = [i for i, b in enumerate(blocks) if b.text == "Item 1A"]
    late = page_headers[2]
    fake = replace(section, heading_index=late, start=late + 1)
    stored = [p for p in _stored(doc) if int(p.text.split()[2]) >= 6]  # risks 6..9 only
    assert len(stored) == 4
    rec = ce.reconcile(ce.raw_text(doc), blocks, seg.sections, fake, stored)
    assert rec.not_found == []
    assert len(rec.unexplained) == 1
    assert rec.unexplained[0].first_words.startswith("Risk number 0 concerns")
    assert not rec.passed
