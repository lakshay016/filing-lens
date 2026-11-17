"""Unit tests for Item segmentation (task 1.4) on synthetic block lists."""

from __future__ import annotations

from datetime import date

import pytest

from filinglens.parse.html import Block
from filinglens.parse.items import (
    ITEM_ORDER,
    Candidate,
    choose_headings,
    find_candidates,
    item_status,
    segment,
)

Spec = tuple[str, str | int]

TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements With Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "10": "Directors, Executive Officers and Corporate Governance",
}


def doc(*specs: Spec) -> list[Block]:
    """("h", text) heading, ("s", text) short text block, ("t", n) text block of n chars."""
    blocks: list[Block] = []
    for kind, value in specs:
        if kind == "h":
            blocks.append(Block("heading", str(value), level=1))
        elif kind == "s":
            blocks.append(Block("text", str(value)))
        elif kind == "t":
            assert isinstance(value, int)
            blocks.append(Block("text", "a" * value))
        else:
            raise AssertionError(kind)
    return blocks


def heading(code: str) -> Spec:
    return ("h", f"Item {code}. {TITLES[code]}")


def toc(codes: tuple[str, ...]) -> list[Spec]:
    return [("s", f"Item {c}. {TITLES[c]}") for c in codes]


ALL = tuple(c for c in ITEM_ORDER if c in TITLES)
SIZES = {"1": 30_000, "1A": 40_000, "7": 25_000, "8": 50_000}


def body(codes: tuple[str, ...] = ALL, sizes: dict[str, int] | None = None) -> list[Spec]:
    sizes = SIZES if sizes is None else sizes
    out: list[Spec] = []
    for code in codes:
        out += [heading(code), ("t", sizes.get(code, 3_000))]
    return out


def toc_doc(codes: tuple[str, ...] = ALL) -> list[Block]:
    return doc(("s", "Cover page"), ("t", 800), ("s", "Table of contents"), *toc(codes), *body(codes))


def test_1_toc_then_body_picks_body_headings() -> None:
    blocks = toc_doc()
    n_toc = len(ALL)
    seg = segment(blocks, date(2023, 12, 31))
    assert seg.status == "ok"
    assert seg.notes["status_reasons"] == []
    body_start = 3 + n_toc  # cover, cover text, "Table of contents", TOC lines
    chosen = {s.item: s.heading_index for s in seg.sections if s.heading_index is not None}
    assert chosen == {code: body_start + 2 * k for k, code in enumerate(ALL)}
    assert seg.notes["n_candidates"] == 2 * len(ALL)
    assert seg.notes["items"]["8"]["chars"] == 50_000
    assert seg.notes["items"]["8"]["n_blocks"] == 1


def test_2_gain_is_to_next_candidate_not_next_chosen() -> None:
    # The trap. Gain is measured to the next *candidate*, so a table-of-contents line
    # (next candidate one block away) has a gain near zero. Measured to the next *chosen*
    # heading it would telescope, and the TOC "Item 1" followed by the body "Item 1A"
    # would beat the body "Item 1".
    blocks = toc_doc()
    toc_item_1 = 3
    body_item_1 = 3 + len(ALL)
    candidates = find_candidates(blocks)
    by_index = {c.block_index: c for c in candidates}
    assert by_index[toc_item_1].gain == 0  # the next candidate is the very next block
    assert by_index[body_item_1].gain == 30_000

    seg = segment(blocks, date(2023, 12, 31))
    item_1 = next(s for s in seg.sections if s.item == "1")
    assert item_1.heading_index == body_item_1
    assert item_1.heading_index != toc_item_1
    front = seg.sections[0]
    assert front.item == "front" and front.heading_index is None
    assert front.start == 0 and front.end == body_item_1
    assert front.start <= toc_item_1 < front.end  # the table of contents sits in `front`


def test_3_stray_cross_reference_does_not_cut_section() -> None:
    specs = [*toc(ALL)]
    for code in ALL:
        specs += [heading(code), ("t", SIZES.get(code, 3_000))]
        if code == "7":
            specs += [("s", "Item 1A. Risk Factors"), ("t", 1_000)]
    blocks = doc(*specs)
    seg = segment(blocks, date(2023, 12, 31))
    assert seg.status == "ok"
    sec7 = next(s for s in seg.sections if s.item == "7")
    assert sec7.chars == 25_000 + len("Item 1A. Risk Factors") + 1_000
    assert [s.item for s in seg.sections if s.item == "1A"] == ["1A"]
    sec1a = next(s for s in seg.sections if s.item == "1A")
    assert sec1a.chars == 40_000


def test_4_stray_forward_reference_loses_to_real_heading() -> None:
    specs: list[Spec] = []
    for code in ALL:
        specs += [heading(code), ("t", SIZES.get(code, 3_000))]
        if code == "7":
            specs += [("s", "Item 8. Financial Statements and Supplementary Data"), ("t", 300)]
    blocks = doc(*specs)
    seg = segment(blocks, date(2023, 12, 31))
    sec8 = next(s for s in seg.sections if s.item == "8")
    assert blocks[sec8.heading_index or 0].kind == "heading"  # the real one
    assert sec8.chars == 50_000
    sec7 = next(s for s in seg.sections if s.item == "7")
    assert sec7.chars == 25_000 + len("Item 8. Financial Statements and Supplementary Data") + 300
    assert seg.status == "ok"


def test_5_combined_heading() -> None:
    specs: list[Spec] = [("h", "Items 1 and 2. Business and Properties"), ("t", 30_000)]
    for code in ("3", "7", "8"):
        specs += [heading(code), ("t", SIZES.get(code, 3_000))]
    seg = segment(doc(*specs), date(2004, 12, 31))  # before Item 1A existed
    assert seg.status == "ok"
    assert seg.notes["combined"] == {"1": ["2"]}
    assert item_status(seg.notes, "1") == "ok"
    assert item_status(seg.notes, "2") == "ok"
    assert seg.notes["items"]["2"] == {"status": "ok", "combined_into": "1"}
    sec1 = next(s for s in seg.sections if s.item == "1")
    assert sec1.combined == ("2",) and sec1.chars == 30_000
    assert not any(s.item == "2" for s in seg.sections)


def test_5b_combined_heading_order_constraint() -> None:
    both = [Candidate(0, ("1", "2"), 100), Candidate(10, ("3",), 100)]
    assert choose_headings(both) == both  # combined 1,2 followed by 3 is legal
    clash = [Candidate(0, ("1", "2"), 100), Candidate(10, ("2",), 100)]
    assert len(choose_headings(clash)) == 1  # followed by 2 is not
    heavy_two = [Candidate(0, ("1", "2"), 100), Candidate(10, ("2",), 500)]
    assert choose_headings(heavy_two) == [heavy_two[1]]
    # every code of a combined heading must come after the previous chosen candidate
    overlap = [Candidate(0, ("2",), 100), Candidate(10, ("1", "2"), 100)]
    assert len(choose_headings(overlap)) == 1


def test_6_item_1a_depends_on_era() -> None:
    codes = ("1", "2", "3", "7", "8", "9")
    blocks = doc(*body(codes))
    old = segment(blocks, date(2004, 12, 31))
    assert old.status == "ok"
    new = segment(blocks, date(2010, 12, 31))
    assert new.status == "partial"
    assert new.notes["status_reasons"] == ["missing:1A"]
    assert segment(blocks, None).status == "partial"  # unknown period: 1A is expected


def test_7_short_item_7_is_partial() -> None:
    blocks = doc(*body(ALL, {**SIZES, "7": 300}))
    seg = segment(blocks, date(2023, 12, 31))
    assert seg.status == "partial"
    assert seg.notes["status_reasons"] == ["short:7"]
    assert item_status(seg.notes, "7") == "short"
    assert item_status(seg.notes, "8") == "ok"


def test_8_failed_documents() -> None:
    two = segment(doc(*body(("1", "7"))), date(2023, 12, 31))
    assert two.status == "failed"
    assert "too_few_items" in two.notes["status_reasons"]
    tiny = segment(doc(*body(("1", "1A", "7", "8"), {c: 1_200 for c in SIZES})), None)
    assert tiny.status == "failed"
    assert tiny.notes["status_reasons"] == ["too_short"]
    assert segment([], None).status == "failed"


@pytest.mark.parametrize(
    ("kind", "text", "codes"),
    [
        ("heading", "ITEM 7A—QUANTITATIVE AND QUALITATIVE DISCLOSURES", ("7A",)),
        ("heading", "Item 9A(T). Controls and Procedures", ("9A",)),
        ("heading", "Item 1A: Risk Factors", ("1A",)),
        ("text", "item 5 .", ("5",)),
        ("heading", "Items 1 and 2. Business and Properties", ("1", "2")),
        ("heading", "ITEMS 1, 1A & 2 - Business", ("1", "1A", "2")),
        ("heading", "Item 17. Something", None),
        ("heading", "Item 1ABusiness", None),
        ("heading", "Items 2 and 1. Out of order", None),
        ("table", "Item 1. Business", None),
    ],
)
def test_9_candidate_patterns(kind: str, text: str, codes: tuple[str, ...] | None) -> None:
    found = find_candidates([Block(kind, text)])  # type: ignore[arg-type]
    assert [c.codes for c in found] == ([codes] if codes else [])


def test_10_long_text_block_is_not_a_candidate() -> None:
    long_text = "Item 7 of this report" + " x" * 240
    assert len(long_text) > 200
    assert find_candidates([Block("text", long_text)]) == []
    assert find_candidates([Block("text", "Item 7 of this report")])  # short: a candidate
    assert find_candidates([Block("heading", long_text)])  # headings have no length cap


def test_11_out_of_order_keeps_better_subset() -> None:
    specs: list[Spec] = []
    for code in ("1", "1A", "8", "7", "9"):
        specs += [heading(code), ("t", {"8": 40_000, "7": 10_000}.get(code, SIZES.get(code, 3_000)))]
    seg = segment(doc(*specs), date(2023, 12, 31))
    found = [s.item for s in seg.sections if s.heading_index is not None]
    assert found == ["1", "1A", "8", "9"]
    assert seg.status == "partial"
    assert seg.notes["status_reasons"] == ["missing:7"]


def test_12_determinism_and_empty() -> None:
    blocks = toc_doc()
    assert segment(blocks, date(2022, 6, 30)) == segment(blocks, date(2022, 6, 30))
    assert choose_headings([]) == []
    assert find_candidates([]) == []


def test_tie_prefers_later_block() -> None:
    cands = [Candidate(5, ("1",), 100), Candidate(9, ("1",), 100)]
    assert choose_headings(cands) == [cands[1]]


def test_item_status_missing() -> None:
    assert item_status({"items": {}}, "7") == "missing"
    assert item_status({}, "7") == "missing"
