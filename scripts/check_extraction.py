"""Source-only extraction completeness check for one filing and one Item.

    uv run python scripts/check_extraction.py --accession 0000320193-22-000108 --item 1A

Checks ONE filing at a time against its own stored raw document; it never compares two
filings. It reads the stored raw file and the stored paragraphs, and reports

1. the body heading of the Item (and every other mention of it), with a pass/fail that
   the chosen heading is the body one rather than a table-of-contents entry;
2. an interior reconciliation: the Item's text is rebuilt from the raw HTML without the
   project's block extractor (lxml text in order, hidden content dropped), every stored
   paragraph is located in it in order, and every uncovered stretch longer than 40
   characters is listed and classified (heading, page number, running header/footer,
   table-of-contents link text) or called "unexplained".

Exit code 0 when the heading check passes, every paragraph is found in order and nothing
is unexplained; 1 otherwise. Reads settings through ``filinglens.config`` (nothing is
printed from them) and needs no network.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

import lxml.html
import sqlalchemy as sa
from lxml import etree

from filinglens.config import get_settings
from filinglens.db.models import Filing, Paragraph
from filinglens.db.session import session_scope
from filinglens.edgar.store import raw_path, read_raw
from filinglens.parse.html import Block, extract_blocks
from filinglens.parse.items import ITEM_MIN_CHARS, Section, find_candidates, segment

MIN_STRETCH = 40
TOC_ROW_MAX_GAIN = 1000  # "little text between contents entries"
FURNITURE_MIN_REPEATS = 3

_BLOCK_TAGS = frozenset(
    {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "tr", "blockquote"}
    | {"pre", "center", "section", "article", "ul", "ol", "table", "body", "br", "hr"}
)
_DROP_TAGS = frozenset({"script", "style", "ix:header"})
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_ZERO_WIDTH = str.maketrans({"\u200b": None, "\u200c": None, "\u200d": None, "\ufeff": None})
_WS_RE = re.compile(r"\s+")
_PAGE_RE = re.compile(r"(?<![\w.])(?:page\s+)?\d{1,3}(?:\s+of\s+\d+)?(?![\w.])", re.IGNORECASE)
_TOC_RE = re.compile(r"table\s+of\s+contents", re.IGNORECASE)


def norm(text: str) -> str:
    """NFKC, straight quotes, no zero-width characters, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_ZERO_WIDTH)
    return _WS_RE.sub(" ", text).strip()


def words(text: str, n: int = 12) -> str:
    return " ".join(text.split()[:n])


# ------------------------------------------------------------------ raw text, no extractor


def _decode(document: bytes) -> str:
    if document.startswith(b"\xef\xbb\xbf"):
        document = document[3:]
    try:
        return document.decode("utf-8")
    except UnicodeDecodeError:
        return document.decode("latin-1")


def _is_hidden(el: etree._Element) -> bool:
    style = el.get("style")
    return bool(style) and "display:none" in "".join(style.split()).lower()


def _emit(el: etree._Element, out: list[str | None]) -> None:
    tag = el.tag.lower() if isinstance(el.tag, str) else ""
    block = tag in _BLOCK_TAGS
    if block:
        out.append(None)
    if el.text:
        out.append(el.text)
    for child in el:
        _emit(child, out)
        if child.tail:
            out.append(child.tail)
    if block:
        out.append(None)


@dataclass(frozen=True, slots=True)
class RawText:
    text: str  # normalised lines joined by one space
    lines: tuple[str, ...]
    line_starts: frozenset[int]  # offsets in ``text`` at which a block-level line starts


def raw_text(document: bytes) -> RawText:
    """Document text in order: drop script, style, ix:header and display:none elements."""
    text = _decode(document)
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1)
    root = lxml.html.document_fromstring(text, parser=lxml.html.HTMLParser(huge_tree=True))
    for el in list(root.iter()):
        if el is root:
            continue
        tag = el.tag
        if not isinstance(tag, str) or tag.lower() in _DROP_TAGS or _is_hidden(el):
            el.drop_tree()  # type: ignore[attr-defined]  # keeps the tail text
    parts: list[str | None] = []
    _emit(root, parts)
    lines: list[str] = []
    current: list[str] = []
    for part in [*parts, None]:
        if part is None:
            line = norm("".join(current))
            if line:
                lines.append(line)
            current = []
        else:
            current.append(part)
    starts: set[int] = set()
    offset = 0
    for line in lines:
        starts.add(offset)
        offset += len(line) + 1
    return RawText(" ".join(lines), tuple(lines), frozenset(starts))


# ------------------------------------------------------------------ heading check


@dataclass(frozen=True, slots=True)
class Mention:
    index: int
    kind: str
    chars: int
    text: str
    chosen: bool
    gain: int | None  # characters up to the next Item candidate; None if not a candidate


@dataclass(slots=True)
class HeadingResult:
    item: str
    heading_index: int | None = None
    heading_text: str = ""
    section_chars: int = 0
    n_blocks_total: int = 0
    mentions: list[Mention] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.heading_index is not None and not self.problems


def _mentions_item(text: str, item: str) -> bool:
    return (
        re.search(rf"\bitems?\s+(?:\d{{1,2}}[abc]?\s*(?:,|and|&)\s*)*{item}\b", text, re.I)
        is not None
    )


def check_heading(blocks: Sequence[Block], section: Section | None, item: str) -> HeadingResult:
    result = HeadingResult(item=item, n_blocks_total=len(blocks))
    candidates = {c.block_index: c for c in find_candidates(blocks)}
    if section is None or section.heading_index is None:
        result.problems.append(f"no section for Item {item} in the segmentation")
        return result
    result.heading_index = section.heading_index
    result.heading_text = blocks[section.heading_index].text
    result.section_chars = section.chars
    for i, block in enumerate(blocks):
        if not _mentions_item(block.text, item):
            continue
        cand = candidates.get(i)
        result.mentions.append(
            Mention(
                i, block.kind, len(block.text), block.text, i == section.heading_index,
                cand.gain if cand else None,
            )
        )  # fmt: skip
    others = [
        c.gain for i, c in candidates.items() if i != section.heading_index and item in c.codes
    ]
    if section.chars < ITEM_MIN_CHARS:
        result.problems.append(f"chosen section has only {section.chars} characters")
    if others and max(others) > section.chars:
        result.problems.append(f"another {item} heading leads to a larger section ({max(others)})")
    for i, c in candidates.items():
        if item in c.codes and i < section.heading_index and c.gain > TOC_ROW_MAX_GAIN:
            result.problems.append(
                f"an earlier {item} heading (block {i}) has {c.gain} characters after it"
            )
    return result


# ------------------------------------------------------------------ reconciliation


@dataclass(frozen=True, slots=True)
class StoredParagraph:
    seq: int
    text: str
    is_table: bool = False
    heading_path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Stretch:
    start: int
    length: int
    first_words: str
    classification: str  # "unexplained" or what it is


@dataclass(frozen=True, slots=True)
class NotFound:
    seq: int
    first_words: str
    reason: str  # "not found" or "out of order"


@dataclass(slots=True)
class Reconciliation:
    section_chars: int = 0
    start_note: str = ""
    end_note: str = ""
    found: int = 0
    total: int = 0
    not_found: list[NotFound] = field(default_factory=list)
    stretches: list[Stretch] = field(default_factory=list)
    short_gaps: int = 0
    short_gap_chars: int = 0
    covered_chars: int = 0
    error: str = ""

    @property
    def coverage(self) -> float:
        return self.covered_chars / self.section_chars if self.section_chars else 0.0

    @property
    def unexplained(self) -> list[Stretch]:
        return [s for s in self.stretches if s.classification.startswith("unexplained")]

    @property
    def passed(self) -> bool:
        return not self.error and not self.not_found and not self.unexplained


def _line_start_occurrences(raw: RawText, needle: str, lo: int = 0) -> list[int]:
    found: list[int] = []
    pos = raw.text.find(needle, lo)
    while pos != -1:
        if pos in raw.line_starts:
            found.append(pos)
        pos = raw.text.find(needle, pos + 1)
    return found


def _squash(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            index.append(i)
    return "".join(chars), index


def _locate(section: str, text: str, cursor: int, is_table: bool) -> list[tuple[int, int]] | None:
    """Intervals of ``section`` (at or after ``cursor``) holding ``text``, or None."""
    i = section.find(text, cursor)
    if i != -1:
        return [(i, i + len(text))]
    ws = text.split(" ")
    pos, w = cursor, 0
    spans: list[tuple[int, int]] = []
    while w < len(ws):  # a glued paragraph: locate its parts one after another
        lo, hi = 0, len(ws) - w
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if section.find(" ".join(ws[w : w + mid]), pos) != -1:
                lo = mid
            else:
                hi = mid - 1
        if lo == 0:
            spans = []
            break
        chunk = " ".join(ws[w : w + lo])
        i = section.find(chunk, pos)
        spans.append((i, i + len(chunk)))
        pos, w = i + len(chunk), w + lo
    if spans:
        return spans
    if is_table:  # table cells are joined differently in the raw text
        sq_text, _ = _squash(text)
        sq_sec, idx = _squash(section)
        first_char = next((k for k, j in enumerate(idx) if j >= cursor), len(idx))
        k = sq_sec.find(sq_text, first_char) if sq_text else -1
        if k != -1:
            return [(idx[k], idx[k + len(sq_text) - 1] + 1)]
    return None


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _furniture(lines: Sequence[str]) -> list[re.Pattern[str]]:
    counts = Counter(re.sub(r"\d+", "#", line) for line in lines if len(line) <= 200)
    patterns: list[re.Pattern[str]] = []
    for masked, n in sorted(counts.items(), key=lambda kv: -len(kv[0])):
        if n >= FURNITURE_MIN_REPEATS and re.search(r"[A-Za-z]", masked):
            patterns.append(re.compile(r"\d+".join(map(re.escape, masked.split("#")))))
    return patterns


def _classify(gap: str, furniture: Sequence[re.Pattern[str]], headings: Sequence[str]) -> str:
    residual = gap
    seen: list[str] = []

    def strip(label: str, pattern: re.Pattern[str]) -> None:
        nonlocal residual
        new = pattern.sub(" ", residual)
        if new != residual:
            residual = new
            if label not in seen:
                seen.append(label)

    strip("table-of-contents link text", _TOC_RE)
    for pattern in furniture:
        strip("running header/footer", pattern)
    for heading in sorted(headings, key=len, reverse=True):
        strip("heading", re.compile(re.escape(heading)))
    strip("page number", _PAGE_RE)
    left = re.sub(r"[\W_]+", " ", residual).strip()
    if left:
        return f"unexplained (after removing {', '.join(seen) or 'nothing'}: {words(left)!r})"
    return ", ".join(seen) if seen else "unexplained"


def reconcile(
    raw: RawText,
    blocks: Sequence[Block],
    sections: Sequence[Section],
    section: Section,
    stored: Sequence[StoredParagraph],
    min_stretch: int = MIN_STRETCH,
) -> Reconciliation:
    rec = Reconciliation(total=len(stored))
    assert section.heading_index is not None
    heading = norm(blocks[section.heading_index].text)
    occurrences = _line_start_occurrences(raw, heading)
    if not occurrences:
        rec.error = f"heading {heading!r} not found in the raw text"
        return rec
    # The body heading is the last occurrence before the first stored paragraph's text.
    n = len(occurrences) - 1
    if stored:
        probe = norm(min(stored, key=lambda x: x.seq).text)[:60]
        at = raw.text.find(probe, occurrences[0])
        if at != -1:
            n = max((k for k, o in enumerate(occurrences) if o < at), default=0)
    start = occurrences[n]
    rec.start_note = f"heading occurrence {n + 1} of {len(occurrences)} in the raw text"
    later = [s for s in sections if s.heading_index is not None and s.start >= section.end]
    end = len(raw.text)
    rec.end_note = "end of document"
    if later:
        nxt = norm(blocks[later[0].heading_index or 0].text)
        after = [o for o in _line_start_occurrences(raw, nxt, start + len(heading)) if o > start]
        if after:
            end = after[0]
            rec.end_note = f"next heading {nxt!r}"
        else:
            rec.error = f"next heading {nxt!r} not found after the Item heading"
            return rec
    s = raw.text[start:end].rstrip()
    rec.section_chars = len(s)

    intervals: list[tuple[int, int]] = [(0, len(heading))]
    cursor = len(heading)
    prev_path: tuple[str, ...] = ()
    for p in sorted(stored, key=lambda x: x.seq):
        text = norm(p.text)
        spans = _locate(s, text, cursor, p.is_table)
        if spans is None:
            earlier = s.find(text, 0) if text else -1
            reason = "out of order" if 0 <= earlier < cursor else "not found"
            rec.not_found.append(NotFound(p.seq, words(text), reason))
            continue
        common = 0
        while common < min(len(prev_path), len(p.heading_path)) and (
            prev_path[common] == p.heading_path[common]
        ):
            common += 1
        window_start = cursor
        for h in p.heading_path[common:]:
            ht = norm(h)
            at = s.find(ht, window_start, spans[0][0]) if ht else -1
            if at != -1:
                intervals.append((at, at + len(ht)))
                window_start = at + len(ht)
        prev_path = p.heading_path
        intervals += spans
        cursor = spans[-1][1]
        rec.found += 1

    merged = _merge(intervals)
    rec.covered_chars = sum(b - a for a, b in merged)
    heading_texts = sorted({norm(b.text) for b in blocks[section.start : section.end]
                            if b.kind == "heading" and b.text.strip()})  # fmt: skip
    furniture = _furniture(raw.lines)
    gaps: list[tuple[int, int]] = []
    last = 0
    for a, b in [*merged, (len(s), len(s))]:
        if a > last:
            gaps.append((last, a))
        last = max(last, b)
    for a, b in gaps:
        gap = s[a:b].strip()
        if not gap:
            continue
        if len(gap) <= min_stretch:
            rec.short_gaps += 1
            rec.short_gap_chars += len(gap)
            continue
        rec.stretches.append(
            Stretch(a, len(gap), words(gap), _classify(gap, furniture, heading_texts))
        )
    return rec


# ------------------------------------------------------------------ top level


@dataclass(slots=True)
class Report:
    accession: str
    item: str
    heading: HeadingResult
    recon: Reconciliation

    @property
    def passed(self) -> bool:
        return self.heading.passed and self.recon.passed


def analyse(
    document: bytes, stored: Sequence[StoredParagraph], item: str, accession: str = ""
) -> Report:
    blocks = extract_blocks(document)
    seg = segment(blocks, None)
    section = next(
        (s for s in seg.sections if s.item == item and s.heading_index is not None), None
    )
    heading = check_heading(blocks, section, item)
    if section is None:
        return Report(accession, item, heading, Reconciliation(error="no section to reconcile"))
    recon = reconcile(raw_text(document), blocks, seg.sections, section, stored)
    return Report(accession, item, heading, recon)


def render(report: Report) -> str:
    h, r = report.heading, report.recon
    out = [f"Extraction completeness: {report.accession} Item {report.item}", "", "1. Body heading"]
    if h.heading_index is not None:
        out.append(
            f"  chosen: block {h.heading_index} of {h.n_blocks_total}: {h.heading_text!r}; "
            f"section {h.section_chars} characters"
        )
    out.append("  every block mentioning the Item:")
    for m in h.mentions:
        gain = "-" if m.gain is None else str(m.gain)
        mark = "CHOSEN" if m.chosen else "      "
        out.append(f"    {mark} block {m.index:>4} {m.kind:<7} {m.chars:>5} chars, "
                   f"text after it {gain:>6}: {words(m.text, 14)!r}")  # fmt: skip
    out.append(
        f"  result: {'PASS' if h.passed else 'FAIL'}" + "".join(f"\n    - {p}" for p in h.problems)
    )
    out += ["", "2. Interior reconciliation"]
    if r.error:
        out.append(f"  ERROR: {r.error}")
    else:
        out += [
            f"  raw section: {r.section_chars} characters ({r.start_note}; end: {r.end_note})",
            f"  paragraphs found in order: {r.found} / {r.total}",
            f"  coverage: {100 * r.coverage:.2f}% ({r.covered_chars} / {r.section_chars})",
            f"  uncovered gaps of {MIN_STRETCH} characters or fewer: {r.short_gaps} "
            f"({r.short_gap_chars} characters)",
        ]
        for nf in r.not_found:
            out.append(f"  paragraph seq {nf.seq} {nf.reason}: {nf.first_words!r}")
        out.append(f"  uncovered stretches over {MIN_STRETCH} characters: {len(r.stretches)}")
        for st in r.stretches:
            out.append(
                f"    at {st.start}, {st.length} chars, {st.classification}: {st.first_words!r}"
            )
    out += ["", f"OVERALL: {'PASS' if report.passed else 'FAIL'}"]
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    parser.add_argument("--accession", required=True)
    parser.add_argument("--item", required=True)
    args = parser.parse_args(argv)
    item = args.item.upper()
    with session_scope() as session:
        filing = session.scalars(
            sa.select(Filing).where(Filing.accession == args.accession)
        ).first()
        if filing is None:
            print(f"no filing with accession {args.accession}", file=sys.stderr)
            return 2
        path = raw_path(
            get_settings().data_dir, filing.cik, filing.accession, filing.primary_document
        )
        rows = session.scalars(
            sa.select(Paragraph)
            .where(Paragraph.filing_id == filing.id, Paragraph.item == item)
            .order_by(Paragraph.seq)
        ).all()
        stored = [StoredParagraph(p.seq, p.text, p.is_table, tuple(p.heading_path)) for p in rows]
    report = analyse(read_raw(path), stored, item, args.accession)
    print(render(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
