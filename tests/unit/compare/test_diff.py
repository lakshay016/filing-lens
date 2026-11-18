from __future__ import annotations

import pytest

from filinglens.compare.diff import Op, compare_key, diff_paragraphs, word_diff
from filinglens.compare.load import Para


def paras(*texts: str) -> list[Para]:
    return [
        Para(seq=i, n=i + 1, heading_path=(), text=t, is_table=False) for i, t in enumerate(texts)
    ]


def kinds(ops: list[Op]) -> list[str]:
    return [o.kind for o in ops]


def test_identical_lists_are_one_equal_op() -> None:
    a = paras("one", "two", "three")
    ops = diff_paragraphs(a, paras("one", "two", "three"))
    assert kinds(ops) == ["equal"]
    assert len(ops[0].old) == len(ops[0].new) == 3


def test_added_and_removed() -> None:
    ops = diff_paragraphs(paras("a", "b", "c"), paras("a", "c", "d"))
    assert kinds(ops) == ["equal", "removed", "equal", "added"]
    assert [p.text for p in ops[1].old] == ["b"] and ops[1].new == ()
    assert [p.text for p in ops[3].new] == ["d"] and ops[3].old == ()


def test_number_change_is_replaced_one_by_one() -> None:
    ops = diff_paragraphs(
        paras("keep", "Revenue fell 12 percent in 2022.", "end"),
        paras("keep", "Revenue fell 15 percent in 2022.", "end"),
    )
    assert kinds(ops) == ["equal", "replaced", "equal"]
    assert len(ops[1].old) == 1 and len(ops[1].new) == 1


def test_moved_paragraph_is_removed_and_added() -> None:
    ops = diff_paragraphs(paras("a", "b", "c", "d"), paras("b", "c", "d", "a"))
    assert sorted(kinds(ops)) == ["added", "equal", "removed"]
    removed = next(o for o in ops if o.kind == "removed")
    added = next(o for o in ops if o.kind == "added")
    assert [p.text for p in removed.old] == ["a"] and [p.text for p in added.new] == ["a"]


def test_two_edited_paragraphs_form_one_group_without_pairing() -> None:
    ops = diff_paragraphs(
        paras("same", "old first", "old second", "tail"),
        paras("same", "new first", "new second", "tail"),
    )
    assert kinds(ops) == ["equal", "replaced", "equal"]
    group = ops[1]
    assert [p.text for p in group.old] == ["old first", "old second"]
    assert [p.text for p in group.new] == ["new first", "new second"]


def test_case_only_change_is_equal() -> None:
    ops = diff_paragraphs(paras("Hello, World!"), paras("hello, world!"))
    assert kinds(ops) == ["equal"]


def test_empty_sides() -> None:
    assert diff_paragraphs([], []) == []
    assert kinds(diff_paragraphs([], paras("x"))) == ["added"]
    assert kinds(diff_paragraphs(paras("x"), [])) == ["removed"]


def test_word_diff_one_word_change() -> None:
    assert word_diff("the risk is high", "the risk is low") == [
        ("same", "the risk is"),
        ("del", "high"),
        ("ins", "low"),
    ]


def test_word_diff_identical() -> None:
    assert word_diff("a b", "a b") == [("same", "a b")]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (
            "Net income increased 5% to $1.2 billion.",
            "Net income decreased (5%) to $1.2 billion.",
        ),
        ("a change of 5%", "a change of -5%"),
        ("a loss of (3,400)", "a loss of 3,400"),
        ("$5 million", "\u20ac5 million"),
        ("less than <10%", "less than >10%"),
    ],
)
def test_compare_key_keeps_meaning(a: str, b: str) -> None:
    assert compare_key(a) != compare_key(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Risk   relating to\n China.", "Risk relating to China."),
        ("It\u2019s \u201cmaterial\u201d.", 'It\'s "material".'),
        ("RISK FACTORS", "Risk Factors"),
        ("a\u00a0b", "a b"),
    ],
)
def test_compare_key_folds_form_only(a: str, b: str) -> None:
    assert compare_key(a) == compare_key(b)


def test_sign_change_is_a_one_by_one_replacement() -> None:
    ops = diff_paragraphs(paras("p", "loss of (3,400)"), paras("p", "loss of 3,400"))
    assert kinds(ops) == ["equal", "replaced"]
    assert len(ops[1].old) == 1 and len(ops[1].new) == 1
