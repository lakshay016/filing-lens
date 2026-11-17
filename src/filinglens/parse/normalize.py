"""Text normalisation and hashes for paragraphs (SPEC §5.5, brief 1.5).

Used for hashing and similarity only, never for display. ``norm_masked`` masks dates,
years and numbers *before* stripping punctuation, because ``$1.2 billion`` and
``December 31, 2023`` cannot be recognised afterwards (SPEC §16, 2026-11-15).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from re import Match

_LETTER = r"[^\W\d_]"  # any Unicode letter
_SIGNS = "-\u2013\u2014"  # hyphen-minus, en dash, em dash

_MONTH = (
    r"(?:(?:january|february|march|april|may|june|july|august|september|october"
    r"|november|december)"
    r"|(?:jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?)"
)
_DAY = r"\d{1,2}(?:st|nd|rd|th)?"
_YYYY = r"(?:19|20)\d\d(?!\d)"

DATE_RE: re.Pattern[str] = re.compile(
    rf"""
      (?<!{_LETTER}) {_MONTH} \s+ {_DAY} ,? \s+ {_YYYY}                  # december 31, 2023
    | (?<![\d.,]) {_DAY} \s+ (?<!{_LETTER}) {_MONTH} ,? \s+ {_YYYY}      # 31 december 2023
    | (?<!{_LETTER}) {_MONTH} ,? \s+ {_YYYY}                             # december 2023
    | (?<!{_LETTER}) {_MONTH} \s+ {_DAY} (?!{_LETTER}) (?!\d|[.,]\d)     # december 31
    | (?<![\d/.]) \d{{1,2}} / \d{{1,2}} / (?:\d{{4}}|\d{{2}}) (?![\d/])   # 12/31/2023
    | (?<!\d) (?:19|20)\d\d - (?:0[1-9]|1[0-2]) - (?:0[1-9]|[12]\d|3[01]) (?!\d)  # ISO
    """,
    re.VERBOSE | re.IGNORECASE,
)

YEAR_RE: re.Pattern[str] = re.compile(
    rf"""
    (?<!{_LETTER})(?<![\d.,$-])
    (?:19|20)\d\d
    (?!{_LETTER})(?![\d%])(?![.,]\d)
    """,
    re.VERBOSE,
)

NUMBER_RE: re.Pattern[str] = re.compile(
    rf"""
    (?P<open>\()?
    (?P<sign>[{_SIGNS}])?
    (?P<cur>[$€£¥]\s?)?
    (?<!{_LETTER})(?<!\d)                    # digits not glued to a letter or digit
    (?>\d[\d,]*+(?:\.\d+)?+|\.\d+)           # atomic: never backtrack into the digits
    (?:(?:bn|mm)(?!{_LETTER})                # 1.2bn, 5mm: scale glued to the digits
      |(?!{_LETTER})(?!-{_LETTER}))          # else not followed by a letter or -letter
    (?:\s?%|\s?(?:percent|per\s?cent|basis\s+points?|bps)(?!{_LETTER}))?
    (?:\s?(?:thousand|million|billion|trillion)(?!{_LETTER}))?
    (?(open)\))                              # closing bracket only if one was opened
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _keep_char(c: str) -> str:
    return c if c.isalnum() else " "


def _mask_number(m: Match[str]) -> str:
    s = m.string
    sign = m.group("sign")
    if sign == "-":
        # a hyphenated code (10b5-1, covid-19, s-3): digits after letters-and-digits
        # containing a letter keep their digits
        i = m.start("sign")
        j = i
        while j > 0 and s[j - 1].isalnum():
            j -= 1
        if j < i and any(c.isalpha() for c in s[j:i]):
            return m.group(0)
    # padded so the placeholder never glues to a neighbour; whitespace is collapsed later
    return " <num> "


def norm_exact(text: str) -> str:
    s = unicodedata.normalize("NFKC", text).lower()
    return " ".join("".join(map(_keep_char, s)).split())


def norm_masked(text: str) -> str:
    s = unicodedata.normalize("NFKC", text).lower()
    s = s.replace("<", " ").replace(">", " ")
    s = DATE_RE.sub("<date>", s)
    s = YEAR_RE.sub("<year>", s)
    s = NUMBER_RE.sub(_mask_number, s)
    s = "".join(c if (c.isalnum() or c in "<>") else " " for c in s)
    return " ".join(s.split())


def sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def count_tokens(text: str) -> int:
    return len(norm_exact(text).split())


def exact_hash(text: str) -> str:
    return sha1_hex(norm_exact(text))


def masked_hash(text: str) -> str:
    return sha1_hex(norm_masked(text))
