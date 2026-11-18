"""Baseline paragraph diff: SequenceMatcher on lightly normalised text (brief R1).

Deliberately simple. A moved paragraph shows as removed in one place and added in
another; a ``replaced`` group lists all old and all new paragraphs of the block and never
pairs them by position.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from filinglens.compare.load import Para

OpKind = Literal["equal", "added", "removed", "replaced"]
WordKind = Literal["same", "del", "ins"]


_QUOTES = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
    }
)
_SPACE = re.compile(r"\s+")


def compare_key(text: str) -> str:
    """Paragraph equality key: NFKC, lower case, straight quotes, single spaces.

    Nothing else is removed. Punctuation, signs, brackets, currency symbols, ``%``,
    ``<`` and ``>`` stay, so a sign or unit change is a change.
    """
    folded = unicodedata.normalize("NFKC", text).lower().translate(_QUOTES)
    return _SPACE.sub(" ", folded).strip()


@dataclass(frozen=True, slots=True)
class Op:
    kind: OpKind
    old: tuple[Para, ...]
    new: tuple[Para, ...]


def diff_paragraphs(old: Sequence[Para], new: Sequence[Para]) -> list[Op]:
    old_keys = [compare_key(p.text) for p in old]
    new_keys = [compare_key(p.text) for p in new]
    matcher = difflib.SequenceMatcher(None, old_keys, new_keys, autojunk=False)
    ops: list[Op] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        old_part, new_part = tuple(old[i1:i2]), tuple(new[j1:j2])
        if tag == "equal":
            ops.append(Op("equal", old_part, new_part))
        elif tag == "delete":
            ops.append(Op("removed", old_part, ()))
        elif tag == "insert":
            ops.append(Op("added", (), new_part))
        else:
            ops.append(Op("replaced", old_part, new_part))
    return ops


def word_diff(old_text: str, new_text: str) -> list[tuple[WordKind, str]]:
    """Whitespace-token diff of the original text; adjacent same-kind runs are joined."""
    old_words, new_words = old_text.split(), new_text.split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    out: list[tuple[WordKind, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.append(("same", " ".join(old_words[i1:i2])))
            continue
        if i2 > i1:
            out.append(("del", " ".join(old_words[i1:i2])))
        if j2 > j1:
            out.append(("ins", " ".join(new_words[j1:j2])))
    return out
