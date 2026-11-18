"""Item segmentation of a block list (SPEC §5.4, §16 rows of 2026-11-15, brief 1.4).

``segment`` is pure and deterministic. Candidate Item headings are found with a pattern;
a small dynamic programme picks the in-order subsequence of candidates that maximises the
sum of their *gains*, where the gain of a candidate is the text up to the next candidate
of any Item. A section then runs from its chosen heading to the next *chosen* heading.

Running Item headers (brief R2-repeated-item-headers): some filers print a bare page
header such as ``Item 1A`` at the top of every page of a section. A candidate whose
normalised text occurs ``RUNNING_HEADER_MIN_REPEATS`` or more times among the document's
candidates is a running header and is removed before gains are computed, so the true
heading's gain runs to the next real candidate. If that leaves an Item code with no
candidate, the first running-header occurrence for that code is restored (the first one
followed by at least ``ITEM_MIN_CHARS`` characters before the next remaining candidate,
so a table-of-contents line is passed over; the very first if none is).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from filinglens.parse.html import Block

ITEM_ORDER = (
    "1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8",
    "9", "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16",
)  # fmt: skip
FRONT = "front"
REQUIRED_ITEMS = ("1", "7", "8")
ITEM_1A_FROM = date(2005, 12, 1)  # fiscal years ending on or after
ITEM_1C_FROM = date(2023, 12, 15)  # informational; 1C is never required
SHORT_CHECKED = ("1", "1A", "7", "8")
ITEM_MIN_CHARS = 2000
DOC_MIN_CHARS = 20_000
CANDIDATE_MAX_TEXT_CHARS = 200
RUNNING_HEADER_MIN_REPEATS = 3

_POSITION = {code: i for i, code in enumerate(ITEM_ORDER)}
_CANDIDATE_RE = re.compile(
    r"^\s*items?\s+(\d{1,2}[abc]?)((?:\s*(?:,|and|&)\s*\d{1,2}[abc]?)*)\b\s*[\.:\-\u2013\u2014]?",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"\d{1,2}[abc]?", re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")


@dataclass(frozen=True, slots=True)
class Candidate:
    block_index: int
    codes: tuple[str, ...]  # primary first
    gain: int


@dataclass(frozen=True, slots=True)
class Section:
    item: str  # an ITEM_ORDER code or "front"
    heading_index: int | None  # block index of the Item heading; None for front
    start: int  # first block index of the body
    end: int  # one past the last block index
    chars: int  # total characters of text and table blocks in the body
    combined: tuple[str, ...]  # other codes sharing this section


@dataclass(frozen=True, slots=True)
class Segmentation:
    sections: tuple[Section, ...]  # front first if non-empty, then document order
    status: Literal["ok", "partial", "failed"]
    notes: dict[str, Any]  # stored in filing.parse_notes
    skip_blocks: frozenset[int] = frozenset()  # removed running headers; not paragraphs


def _codes_of(block: Block) -> tuple[str, ...] | None:
    """The Item codes a block's text starts with, or None if it is not a candidate."""
    if block.kind not in ("heading", "text"):
        return None
    if block.kind == "text" and len(block.text) > CANDIDATE_MAX_TEXT_CHARS:
        return None
    match = _CANDIDATE_RE.match(block.text)
    if match is None:
        return None
    codes = (match.group(1), *_CODE_RE.findall(match.group(2)))
    codes = tuple(c.upper() for c in codes)
    if any(c not in _POSITION for c in codes):
        return None
    positions = [_POSITION[c] for c in codes]
    if positions != sorted(set(positions)):  # "Items 2 and 1", "Items 1 and 1": not a heading
        return None
    return codes


def normalise_heading(text: str) -> str:
    """NFKC, lower case, every run of non-letters/digits to one space, trimmed."""
    folded = unicodedata.normalize("NFKC", text).lower()
    return _NON_ALNUM_RE.sub(" ", folded).strip()


@dataclass(frozen=True, slots=True)
class _Screened:
    found: list[tuple[int, tuple[str, ...]]]  # kept candidates: (block index, codes)
    skip: frozenset[int]  # block indices of removed running headers
    running: dict[str, int]  # normalised text -> number of occurrences
    fallback: list[str]  # codes whose first running header was restored


def _screen(blocks: Sequence[Block]) -> _Screened:
    """All pattern candidates, with running Item headers removed (and fallbacks restored)."""
    found = [(i, codes) for i, b in enumerate(blocks) if (codes := _codes_of(b)) is not None]
    keys = [normalise_heading(blocks[i].text) for i, _ in found]
    counts = Counter(keys)
    running = {k: n for k, n in counts.items() if n >= RUNNING_HEADER_MIN_REPEATS}
    kept = [fc for fc, key in zip(found, keys, strict=True) if key not in running]
    removed = [fc for fc, key in zip(found, keys, strict=True) if key in running]
    kept_starts = [i for i, _ in kept]

    def text_to_next_kept(index: int) -> int:
        stop = next((j for j in kept_starts if j > index), len(blocks))
        return sum(len(b.text) for b in blocks[index + 1 : stop])

    covered = {code for _, codes in kept for code in codes}
    restore: dict[int, tuple[str, ...]] = {}
    fallback: list[str] = []
    for code in ITEM_ORDER:
        if code in covered:
            continue
        options = [(i, codes) for i, codes in removed if code in codes]
        if not options:
            continue
        # The first occurrence starts the section. A contents-like occurrence (little text
        # before the next real candidate) is passed over, as the gain rule would do.
        first = next(
            ((i, c) for i, c in options if text_to_next_kept(i) >= ITEM_MIN_CHARS), options[0]
        )
        restore[first[0]] = first[1]
        covered.update(first[1])
        fallback.append(code)
    kept = sorted([*kept, *restore.items()])
    skip = frozenset(i for i, _ in removed if i not in restore)
    return _Screened(kept, skip, dict(sorted(running.items())), fallback)


def _with_gains(
    blocks: Sequence[Block], found: Sequence[tuple[int, tuple[str, ...]]]
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for n, (index, codes) in enumerate(found):
        stop = found[n + 1][0] if n + 1 < len(found) else len(blocks)
        gain = sum(len(b.text) for b in blocks[index + 1 : stop])
        candidates.append(Candidate(index, codes, gain))
    return candidates


def find_candidates(blocks: Sequence[Block]) -> list[Candidate]:
    """Candidate Item headings in document order, each with its gain.

    Running Item headers are not candidates (see the module docstring). The gain is the
    number of characters of block text strictly between the candidate and the next
    candidate (of any Item), or the end of the document for the last one.
    """
    return _with_gains(blocks, _screen(blocks).found)


def choose_headings(candidates: Sequence[Candidate]) -> list[Candidate]:
    """In-order subsequence of candidates with the largest total gain.

    Order constraint: the primary code of each chosen candidate lies after the last code
    of the previously chosen one. Ties prefer the later blocks (chosen block indices
    compared from the last element backwards).
    """
    n = len(candidates)
    first = [_POSITION[c.codes[0]] for c in candidates]
    last = [_POSITION[c.codes[-1]] for c in candidates]
    # best[k] = (total gain, chosen block indices from the end) of the best chain ending at k
    best: list[tuple[int, tuple[int, ...]]] = []
    back: list[int | None] = []
    for k in range(n):
        top: tuple[int, tuple[int, ...]] = (0, ())
        top_p: int | None = None
        for p in range(k):
            if last[p] < first[k] and (best[p][0], best[p][1]) > top:
                top, top_p = best[p], p
        best.append((top[0] + candidates[k].gain, (candidates[k].block_index, *top[1])))
        back.append(top_p)
    if n == 0:
        return []
    end = max(range(n), key=lambda k: best[k])
    chain: list[Candidate] = []
    cursor: int | None = end
    while cursor is not None:
        chain.append(candidates[cursor])
        cursor = back[cursor]
    chain.reverse()
    return chain


def _chars(blocks: Sequence[Block], start: int, end: int) -> int:
    return sum(len(b.text) for b in blocks[start:end])


def segment(blocks: Sequence[Block], period_of_report: date | None) -> Segmentation:
    screened = _screen(blocks)
    candidates = _with_gains(blocks, screened.found)
    chosen = choose_headings(candidates)
    total_chars = _chars(blocks, 0, len(blocks))

    sections: list[Section] = []
    first_heading = chosen[0].block_index if chosen else len(blocks)
    if first_heading > 0:
        sections.append(
            Section(FRONT, None, 0, first_heading, _chars(blocks, 0, first_heading), ())
        )
    for k, cand in enumerate(chosen):
        end = chosen[k + 1].block_index if k + 1 < len(chosen) else len(blocks)
        start = cand.block_index + 1
        sections.append(
            Section(
                item=cand.codes[0],
                heading_index=cand.block_index,
                start=start,
                end=end,
                chars=_chars(blocks, start, end),
                combined=cand.codes[1:],
            )
        )

    items: dict[str, dict[str, Any]] = {}
    combined: dict[str, list[str]] = {}
    for section in sections:
        if section.heading_index is None:
            continue
        items[section.item] = {
            "status": "short"
            if section.item in SHORT_CHECKED and section.chars < ITEM_MIN_CHARS
            else "ok",
            "chars": section.chars,
            "n_blocks": section.end - section.start,
            "heading": blocks[section.heading_index].text,
        }
        if section.combined:
            combined[section.item] = list(section.combined)
            for code in section.combined:
                items[code] = {"status": "ok", "combined_into": section.item}

    reasons: list[str] = []
    status: Literal["ok", "partial", "failed"]
    if len(items) < 3:
        reasons.append("too_few_items")
    if total_chars < DOC_MIN_CHARS:
        reasons.append("too_short")
    if reasons:
        status = "failed"
    else:
        required = list(REQUIRED_ITEMS)
        if period_of_report is None or period_of_report >= ITEM_1A_FROM:
            required.insert(1, "1A")
        for code in required:
            state = items[code]["status"] if code in items else "missing"
            if state != "ok":
                reasons.append(f"{state}:{code}")
        status = "partial" if reasons else "ok"

    notes: dict[str, Any] = {
        "status_reasons": reasons,
        "items": items,
        "combined": combined,
        "n_candidates": len(candidates),
        "total_chars": total_chars,
        "running_headers": screened.running,
        "fallback_headings": screened.fallback,
    }
    return Segmentation(tuple(sections), status, notes, screened.skip)


def item_status(notes: Mapping[str, Any], item: str) -> Literal["ok", "short", "missing"]:
    entry = notes.get("items", {}).get(item)
    if entry is None:
        return "missing"
    return "short" if entry["status"] == "short" else "ok"
