"""Blocks plus an Item segmentation to paragraph records (SPEC §5.5, brief 1.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from filinglens.parse.html import Block
from filinglens.parse.items import Section, Segmentation
from filinglens.parse.normalize import count_tokens, exact_hash, masked_hash, norm_exact

SHORT_CHARS = 40
HEADING_MAX_CHARS = 200


@dataclass(frozen=True, slots=True)
class ParagraphRecord:
    item: str
    seq: int  # 0-based, global within the filing, document order
    heading_path: tuple[str, ...]
    text: str
    is_table: bool
    n_tokens: int
    exact_hash: str
    masked_hash: str


def _section_paragraphs(
    blocks: Sequence[Block], section: Section, first_seq: int, skip: frozenset[int]
) -> list[ParagraphRecord]:
    out: list[ParagraphRecord] = []
    stack: list[tuple[int, str]] = []  # (level, text), outermost first
    pending: list[str] = []  # short text blocks waiting to be glued to the next one

    def emit(text: str, is_table: bool) -> None:
        if not norm_exact(text):  # punctuation-only: nothing to hash or align
            return
        out.append(
            ParagraphRecord(
                item=section.item,
                seq=first_seq + len(out),
                heading_path=tuple(t[:HEADING_MAX_CHARS] for _, t in stack),
                text=text,
                is_table=is_table,
                n_tokens=count_tokens(text),
                exact_hash=exact_hash(text),
                masked_hash=masked_hash(text),
            )
        )

    def flush() -> None:
        if pending:
            emit(" ".join(pending), False)
            pending.clear()

    for index in range(section.start, section.end):
        if index == section.heading_index:
            continue  # the Item's own heading is not part of its path
        if index in skip:
            continue  # a running Item page header: not a paragraph, not in any path
        block = blocks[index]
        if block.kind == "heading":
            flush()  # emitted under the path as it was before this heading
            while stack and stack[-1][0] >= block.level:
                stack.pop()
            stack.append((block.level, block.text))
        elif block.kind == "table":
            flush()
            emit(f"{block.caption}\n{block.text}" if block.caption else block.text, True)
        elif not block.is_list_item and len(block.text) < SHORT_CHARS:
            pending.append(block.text)
        else:
            emit(" ".join([*pending, block.text]), False)
            pending.clear()
    flush()
    return out


def build_paragraphs(blocks: Sequence[Block], segmentation: Segmentation) -> list[ParagraphRecord]:
    out: list[ParagraphRecord] = []
    for section in segmentation.sections:
        out += _section_paragraphs(blocks, section, len(out), segmentation.skip_blocks)
    return out
