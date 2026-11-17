"""HTML primary document to an ordered list of blocks (SPEC §5.3, brief 1.3).

``extract_blocks`` is pure and deterministic. It never raises on malformed markup; it
raises ``NotHtmlError`` only for documents that do not look like HTML at all.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

import lxml.html
from lxml import etree

BlockKind = Literal["text", "table", "heading"]


@dataclass(frozen=True, slots=True)
class Block:
    kind: BlockKind
    text: str
    source_line: int = 0  # lxml sourceline of the block's first element; 0 if unknown
    level: int = 0  # headings only: 1 Item/Part line, 2 all-caps, 3 bold, 4 underline only
    is_list_item: bool = False
    caption: str | None = None  # tables only


class NotHtmlError(ValueError):
    """The document has no HTML structure (plain-text filings are out of scope)."""


_BLOCK_TAGS = frozenset(
    {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "tr", "blockquote"}
    | {"pre", "center", "section", "article", "ul", "ol", "table", "body"}
)
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BOLD_TAGS = frozenset({"b", "strong"})
_DROP_TAGS = frozenset({"script", "style", "head", "title", "ix:header"})

_HTML_SNIFF_RE = re.compile(r"<(html|body|div|p)[\s>/]", re.IGNORECASE)
_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_CHARSET_RE = re.compile(
    rb"""(?:charset|encoding)\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE
)

_EMPTY_CELL_CHARS = frozenset("$%()\u2014\u2013-")  # em dash, en dash, hyphen
_NUMERIC_RE = re.compile(r"^[\(\-\u2013\u2014]?\s*\$?\s*\d[\d,]*(\.\d+)?\s*%?\s*\)?$")
_BULLET_GLYPHS = "\u2022\u00b7\u25cf\u25aa\u25e6\u25a0"  # bullet, middle dot, black circle, ...
_BULLET_START_RE = re.compile(rf"^(?:[{_BULLET_GLYPHS}]|[-\u2013]\s)")
_PAGE_NUMBER_RE = re.compile(r"^(page\s+)?\d{1,3}(\s+of\s+\d+)?$|^[A-Z]-\d{1,3}$", re.IGNORECASE)
_ITEM_EXEMPT_RE = re.compile(r"^\s*items?\s+\d", re.IGNORECASE)
_HEADING_ITEM_RE = re.compile(r"^\s*(items?\s+\d+[abc]?\b|part\s+[iv]+\b)", re.IGNORECASE)
_FURNITURE_PHRASES = frozenset({"table of contents", "index", "back to top"})
_REPEAT_MAX_LEN = 80
_REPEAT_MIN_COUNT = 5
_HEADING_MAX_LEN = 120
_CAPTION_MAX_LEN = 200
_SNIFF_CHARS = 20_000

_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
_ZERO_WIDTH = str.maketrans({"\u200b": None, "\u200c": None, "\u200d": None, "\ufeff": None})
_WS_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_ZERO_WIDTH)
    return _WS_RE.sub(" ", text).strip()


# --------------------------------------------------------------------------- decoding


def _decode(document: bytes) -> str:
    if document.startswith(b"\xef\xbb\xbf"):
        document = document[3:]
    declared = _CHARSET_RE.search(document[:4096])
    candidates: list[str] = []
    if declared:
        candidates.append(declared.group(1).decode("ascii", "replace"))
    candidates += ["utf-8", "latin-1"]
    for encoding in candidates:
        try:
            return document.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return document.decode("latin-1")  # unreachable: latin-1 decodes any byte string


def _parse(document: bytes | str) -> etree._Element | None:
    text = _decode(document) if isinstance(document, bytes) else document
    if not _HTML_SNIFF_RE.search(text[:_SNIFF_CHARS]):
        raise NotHtmlError("no <html, <body, <div or <p tag in the first 20,000 characters")
    text = _XML_DECL_RE.sub("", text, count=1)  # lxml rejects str input with an encoding decl
    parser = lxml.html.HTMLParser(huge_tree=True, remove_blank_text=False)
    try:
        root = lxml.html.document_fromstring(text, parser=parser)
    except (etree.ParserError, ValueError):
        return None
    return root


# --------------------------------------------------------------------------- removal


def _tag(el: etree._Element) -> str:
    tag = el.tag
    return tag.lower() if isinstance(tag, str) else ""


def _line(el: etree._Element) -> int:
    value = el.sourceline
    return value if isinstance(value, int) else 0


def _style_decls(el: etree._Element) -> dict[str, str]:
    style = el.get("style")
    if not style:
        return {}
    decls: dict[str, str] = {}
    for part in style.split(";"):
        name, sep, value = part.partition(":")
        if sep:
            decls[name.strip().lower()] = value.strip().lower()
    return decls


def _is_hidden(el: etree._Element) -> bool:
    style = el.get("style")
    if not style:
        return False
    return "display:none" in "".join(style.split()).lower()


def _remove_dropped(root: etree._Element) -> None:
    """Drop elements listed in rule 1; ``drop_tree`` keeps the tail text."""
    for el in list(root.iter()):
        if el is root:
            continue
        tag = el.tag
        if (
            not isinstance(tag, str)  # comments and processing instructions
            or tag.lower() in _DROP_TAGS
            or _is_hidden(el)
        ):
            el.drop_tree()  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- tables


def _cell_text(cell: etree._Element) -> str:
    parts: list[str] = []

    def collect(el: etree._Element) -> None:
        if el.text:
            parts.append(el.text)
        for child in el:
            tag = _tag(child)
            spaced = tag == "br" or tag in _BLOCK_TAGS
            if spaced:
                parts.append(" ")
            collect(child)
            if spaced:
                parts.append(" ")
            if child.tail:
                parts.append(child.tail)

    collect(cell)
    return _clean("".join(parts))


def _is_empty_cell(text: str) -> bool:
    return all(ch in _EMPTY_CELL_CHARS or ch.isspace() for ch in text)


def _table_rows(table: etree._Element) -> list[list[str]]:
    """Cleaned cell texts per row (empty rows kept as empty lists is not needed)."""
    rows: list[list[str]] = []
    for tr in table.iter("tr", "TR"):
        rows.append([_cell_text(c) for c in tr if _tag(c) in ("td", "th")])
    return rows


def _render_data_table(rows: list[list[str]]) -> str | None:
    """Pipe-delimited rendering, or None when the table is layout (rule 2)."""
    non_empty = [c for row in rows for c in row if not _is_empty_cell(c)]
    if len(non_empty) < 4:
        return None
    numeric = sum(1 for c in non_empty if _NUMERIC_RE.match(c))
    if numeric * 10 < len(non_empty) * 3:
        return None
    lines: list[str] = []
    for row in rows:
        tokens: list[str] = []
        prefix = ""
        for cell in row:
            if cell == "$":
                prefix = "$"
            elif cell in ("%", ")"):
                if tokens:
                    tokens[-1] += cell
            elif not _is_empty_cell(cell):
                tokens.append(prefix + cell)
                prefix = ""
        if tokens:
            lines.append(" | ".join(tokens))
    return "\n".join(lines) if lines else None


# --------------------------------------------------------------------------- walking


@dataclass(slots=True)
class _Raw:
    is_table: bool
    text: str
    line: int
    bold: bool = False
    underline: bool = False
    from_li: bool = False
    from_h: bool = False


def _fmt(el: etree._Element, bold: bool, under: bool) -> tuple[bool, bool]:
    tag = _tag(el)
    if tag in _BOLD_TAGS:
        bold = True
    elif tag == "u":
        under = True
    decls = _style_decls(el)
    weight = decls.get("font-weight")
    if weight is not None:
        bold = weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)
    for name, value in decls.items():
        if name.startswith("text-decoration") and "underline" in value:
            under = True
    return bold, under


class _Walker:
    def __init__(self) -> None:
        self.blocks: list[_Raw] = []
        self._chunks: list[tuple[str, bool, bool]] = []
        self._line = 0
        self._has_text = False
        self._br = 0
        self._li = 0
        self._h = 0

    def _add(self, text: str | None, bold: bool, under: bool, line: int) -> None:
        if not text:
            return
        if text.strip():
            if not self._has_text:
                self._line = line
                self._has_text = True
            self._br = 0
        self._chunks.append((text, bold, under))

    def flush(self) -> None:
        chunks, self._chunks = self._chunks, []
        has_text, self._has_text = self._has_text, False
        self._br = 0
        if not has_text:
            return
        bold = under = True
        for text, b, u in chunks:
            if text.strip():
                bold = bold and b
                under = under and u
        self.blocks.append(
            _Raw(False, "".join(t for t, _, _ in chunks), self._line, bold, under,
                 self._li > 0, self._h > 0)
        )  # fmt: skip

    def walk_children(self, el: etree._Element, bold: bool, under: bool) -> None:
        line = _line(el)
        self._add(el.text, bold, under, line)
        for child in el:
            self.walk(child, bold, under)
            self._add(child.tail, bold, under, line)

    def walk(self, el: etree._Element, bold: bool, under: bool) -> None:
        tag = _tag(el)
        if tag == "br":
            self._br += 1
            if self._br >= 2:
                self.flush()
            else:
                self._chunks.append((" ", bold, under))
            return
        bold, under = _fmt(el, bold, under)
        if tag == "table":
            self._table(el, bold, under)
        elif tag in _BLOCK_TAGS:
            self.flush()
            li = tag == "li"
            h = tag in _HEADING_TAGS
            self._li += li
            self._h += h
            self.walk_children(el, bold, under)
            self.flush()
            self._li -= li
            self._h -= h
        else:
            self.walk_children(el, bold, under)

    def _table(self, el: etree._Element, bold: bool, under: bool) -> None:
        self.flush()
        if el.find(".//table") is None:  # innermost tables only; others are layout
            rendered = _render_data_table(_table_rows(el))
            if rendered is not None:
                self.blocks.append(_Raw(True, rendered, _line(el)))
                return
        self.walk_children(el, bold, under)
        self.flush()


# --------------------------------------------------------------------------- pipeline


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and not any(c.islower() for c in letters)


def _merge_lone_bullets(raws: list[_Raw]) -> list[_Raw]:
    out: list[_Raw] = []
    pending: _Raw | None = None
    for raw in raws:
        if pending is not None:
            if not raw.is_table:
                raw = _Raw(
                    False, f"{pending.text} {raw.text}", pending.line, raw.bold, raw.underline,
                    True, raw.from_h,
                )  # fmt: skip
            else:
                out.append(pending)
            pending = None
        if not raw.is_table and len(raw.text) == 1 and raw.text in _BULLET_GLYPHS:
            pending = raw
        else:
            out.append(raw)
    if pending is not None:
        out.append(pending)
    return out


def _remove_furniture(items: list[tuple[_Raw, bool]]) -> list[tuple[_Raw, bool]]:
    masked = Counter(
        _DIGITS_RE.sub("#", raw.text.lower())
        for raw, _ in items
        if not raw.is_table and len(raw.text) <= _REPEAT_MAX_LEN
    )
    kept: list[tuple[_Raw, bool]] = []
    for raw, is_list in items:
        if raw.is_table:
            kept.append((raw, is_list))
            continue
        text = raw.text
        if _PAGE_NUMBER_RE.match(text) or text.lower() in _FURNITURE_PHRASES:
            continue
        if (
            len(text) <= _REPEAT_MAX_LEN
            and not is_list
            and not _ITEM_EXEMPT_RE.match(text)
            and masked[_DIGITS_RE.sub("#", text.lower())] >= _REPEAT_MIN_COUNT
        ):
            continue
        kept.append((raw, is_list))
    return kept


def _classify(raw: _Raw, is_list: bool) -> tuple[BlockKind, int]:
    text = raw.text
    if len(text) > _HEADING_MAX_LEN or not any(c.isalpha() for c in text) or is_list:
        return "text", 0
    item_like = _HEADING_ITEM_RE.match(text) is not None
    caps = _is_all_caps(text)
    if not (raw.bold or raw.underline or caps or item_like or raw.from_h):
        return "text", 0
    if item_like:
        return "heading", 1
    if raw.from_h or caps:
        return "heading", 2
    if raw.bold:
        return "heading", 3
    return "heading", 4


def extract_blocks(document: bytes | str) -> list[Block]:
    root = _parse(document)
    if root is None:
        return []
    _remove_dropped(root)
    walker = _Walker()
    body = root.find(".//body")
    walker.walk_children(body if body is not None else root, False, False)
    walker.flush()

    cleaned: list[_Raw] = []
    for raw in walker.blocks:
        if raw.is_table:  # cells were cleaned one by one so row newlines survive
            if raw.text:
                cleaned.append(raw)
            continue
        text = _clean(raw.text)
        if text:
            raw.text = text
            cleaned.append(raw)

    items: list[tuple[_Raw, bool]] = []
    for raw in _merge_lone_bullets(cleaned):
        is_list = not raw.is_table and (raw.from_li or _BULLET_START_RE.match(raw.text) is not None)
        items.append((raw, is_list))
    items = _remove_furniture(items)

    blocks: list[Block] = []
    for raw, is_list in items:
        if raw.is_table:
            caption = None
            for prev in reversed(blocks[-2:]):
                if prev.kind != "table" and len(prev.text) <= _CAPTION_MAX_LEN:
                    caption = prev.text
                    break
            blocks.append(Block("table", raw.text, raw.line, caption=caption))
        else:
            kind, level = _classify(raw, is_list)
            blocks.append(Block(kind, raw.text, raw.line, level, is_list))
    return blocks
