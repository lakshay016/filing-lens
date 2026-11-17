"""Unit tests for normalisation and hashes (task 1.5). Every example has an exact output."""

from __future__ import annotations

import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from filinglens.parse.normalize import (
    DATE_RE,
    NUMBER_RE,
    YEAR_RE,
    count_tokens,
    exact_hash,
    masked_hash,
    norm_exact,
    norm_masked,
    sha1_hex,
)

DATES = [
    ("December 31, 2023", "<date>"),
    ("Dec. 31 2023", "<date>"),
    ("December 31st, 2023", "<date>"),
    ("31 December 2023", "<date>"),
    ("1st May 2022", "<date>"),
    ("December 2023", "<date>"),
    ("Sept. 30, 2023", "<date>"),
    ("Sep 2023", "<date>"),
    ("December 31", "<date>"),
    ("March 5th", "<date>"),
    ("12/31/2023", "<date>"),
    ("12/31/23", "<date>"),
    ("2023-12-31", "<date>"),
    ("as of December 31, 2023 and 2022", "as of <date> and <year>"),
    ("the year ended September 30, 2023.", "the year ended <date>"),
    # a month name with neither a day nor a year is left alone
    ("we may increase prices", "we may increase prices"),
    ("they march on", "they march on"),
    ("may", "may"),
    ("March", "march"),
    ("the market 2023", "the market <year>"),  # "mar" inside a word is not a month
]

YEARS = [
    ("fiscal 2023", "fiscal <year>"),
    ("in 2023 and 2022", "in <year> and <year>"),
    ("fiscal 2023.", "fiscal <year>"),
    ("(2022: x)", "<year> x"),
    ("2,023", "<num>"),
    ("$2023", "<num>"),
    ("2023%", "<num>"),
    ("2023.5", "<num>"),
    ("FY2023", "fy2023"),
    ("2022-2023", "<year> <num>"),
    ("1999 to 2001", "<year> to <year>"),
]

NUMBERS = [
    ("$1.2 billion", "<num>"),
    ("$900 million", "<num>"),
    ("12%", "<num>"),
    ("12 %", "<num>"),
    ("12 percent", "<num>"),
    ("12 per cent", "<num>"),
    ("25 basis points", "<num>"),
    ("25 bps", "<num>"),
    ("(3,400)", "<num>"),
    ("-5%", "<num>"),
    ("1,234.56", "<num>"),
    (".5", "<num>"),
    ("€ 7 thousand", "<num>"),
    ("£3 trillion", "<num>"),
    ("1.2bn", "<num>"),
    ("5mm", "<num>"),
    ("(3,400", "<num>"),  # unbalanced opening bracket: the number alone is masked
    ("5-10 million", "<num> <num>"),
    ("approximately 1,200 employees", "approximately <num> employees"),
    ("$3.4 billion (2022: $2.9 billion)", "<num> <year> <num>"),
    # digits glued to a letter, or part of a hyphenated code, are kept
    ("10-K", "10 k"),
    ("10-Q", "10 q"),
    ("Form 8-K", "form 8 k"),
    ("Item 1A", "item 1a"),
    ("Item 7A", "item 7a"),
    ("COVID-19", "covid 19"),
    ("Rule 10b5-1", "rule 10b5 1"),
    ("form S-3", "form s 3"),
    ("G20", "g20"),
    ("3.5x", "3 5x"),
    ("the 2023 10-K", "the <year> 10 k"),
    # a bare number after a word is a number
    ("401(k)", "<num> k"),
    ("Note 12", "note <num>"),
    ("Level 3", "level <num>"),
    ("Level 3 inputs", "level <num> inputs"),
    ("Section 404", "section <num>"),
]

SENTENCES = [
    (
        "Revenue was $1.2 billion in fiscal 2023, up 12% from December 31, 2022.",
        "revenue was <num> in fiscal <year> up <num> from <date>",
    ),
    # the placeholders cannot be forged by the text
    ("a <num> b <date> c", "a num b date c"),
    ("Net sales  rose\n\t9 % (see Note 4)", "net sales rose <num> see note <num>"),
    ("", ""),
    ("   --- ", ""),
]


@pytest.mark.parametrize(
    ("text", "expected"), DATES + YEARS + NUMBERS + SENTENCES, ids=lambda v: repr(v)[:40]
)
def test_norm_masked(text: str, expected: str) -> None:
    assert norm_masked(text) == expected


def test_money_and_percent_variants_mask_equal() -> None:
    assert norm_masked("$1.2 billion") == norm_masked("$900 million")
    pair = (
        "one customer accounted for 10% of revenue",
        "one customer accounted for 35% of revenue",
    )
    assert masked_hash(pair[0]) == masked_hash(pair[1])
    assert exact_hash(pair[0]) != exact_hash(pair[1])


def test_text_differing_only_in_numbers_years_dates_masks_equal() -> None:
    old = "Net sales were $394.3 billion in fiscal 2022, up 7% from September 25, 2021."
    new = "Net sales were $383.3 billion in fiscal 2023, down 3% from September 30, 2022."
    assert norm_masked(old).replace("up", "x") == norm_masked(new).replace("down", "x")
    same_words = old.replace("394.3", "1,000").replace("2022", "2024")
    assert norm_masked(old) == norm_masked(same_words)


def test_texts_differing_in_a_word_mask_differently() -> None:
    assert norm_masked("sales rose 5%") != norm_masked("sales fell 5%")
    assert masked_hash("sales rose 5%") != masked_hash("sales fell 5%")


def test_norm_exact_examples() -> None:
    assert norm_exact("U.S. revenue: $1.2 billion") == "u s revenue 1 2 billion"
    assert norm_exact("  Hello,\n\tWORLD!  ") == "hello world"
    assert norm_exact("") == ""
    assert norm_exact("!!! --- ...") == ""
    assert norm_exact("\uff26\uff55\uff4c\uff4c \uff11\uff12") == "full 12"  # NFKC, fullwidth
    assert norm_exact("Item 1A. Risk Factors") == "item 1a risk factors"
    assert norm_exact("a <num> b") == "a num b"  # exact keeps the digits and words


def test_count_tokens() -> None:
    assert count_tokens("U.S. revenue: $1.2 billion") == 6
    assert count_tokens("") == 0
    assert count_tokens("--- !!!") == 0
    assert count_tokens("one  two\nthree") == 3


def test_hashes() -> None:
    assert sha1_hex("abc") == hashlib.sha1(b"abc").hexdigest()
    assert sha1_hex("é") == hashlib.sha1("é".encode()).hexdigest()
    assert exact_hash("Hello, World") == sha1_hex("hello world")
    assert masked_hash("Up 5% in 2023") == sha1_hex("up <num> in <year>")
    assert len(exact_hash("x")) == 40


def test_exported_patterns() -> None:
    assert DATE_RE.search("on december 31, 2023.")
    assert YEAR_RE.search("fiscal 2023")
    assert NUMBER_RE.search("$1.2 billion")


@given(st.text())
def test_never_raises_and_output_is_lower_case(text: str) -> None:
    for out in (norm_exact(text), norm_masked(text)):
        assert not any(c.isupper() for c in out)
        assert out == " ".join(out.split())
    assert count_tokens(text) >= 0
    assert len(exact_hash(text)) == len(masked_hash(text)) == 40
