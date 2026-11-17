from __future__ import annotations

import pytest

from filinglens.parse.html import _NUMERIC_RE, Block, NotHtmlError, extract_blocks


def blocks(body: str) -> list[Block]:
    return extract_blocks(f"<html><body>{body}</body></html>")


def texts(body: str) -> list[str]:
    return [b.text for b in blocks(body)]


# ---- rule 1: remove -------------------------------------------------------------


def test_hidden_element_dropped_tail_kept() -> None:
    out = texts('<div>Shown <span style="display: none">secret</span> tail</div>')
    assert out == ["Shown tail"]


def test_scripts_styles_comments_dropped() -> None:
    html = (
        "<html><head><title>T</title><style>p{}</style></head><body>"
        "<script>var x=1;</script><!-- note --><p>Body text</p></body></html>"
    )
    assert [b.text for b in extract_blocks(html)] == ["Body text"]


def test_ix_header_dropped_and_ix_nonnumeric_unwrapped() -> None:
    html = (
        "<html><body><div style='display:none'>"
        "<ix:header><ix:hidden>x</ix:hidden></ix:header></div>"
        "<ix:header>HEADER</ix:header>"
        "<p>Revenue was <ix:nonnumeric name='a'>strong</ix:nonnumeric> and "
        "<ix:nonfraction>12</ix:nonfraction> units.</p></body></html>"
    )
    assert [b.text for b in extract_blocks(html)] == ["Revenue was strong and 12 units."]


# ---- rule 2: tables ---------------------------------------------------------------


def _row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def test_data_table_pipe_rows_with_glued_symbols() -> None:
    table = (
        "<table>"
        + _row("Net sales", "$", "1,234", "", "12", "%")
        + _row("Margin", "", "(3,400", ")", "\u2014", "")
        + _row("", "", "")
        + "</table>"
    )
    (block,) = blocks(table)
    assert block.kind == "table"
    assert block.text == "Net sales | $1,234 | 12%\nMargin | (3,400)"


def test_three_by_three_numeric_table_is_data() -> None:
    table = "<table>" + _row("A", "1", "2") + _row("B", "3", "4") + _row("C", "5", "6") + "</table>"
    (block,) = blocks(table)
    assert block.kind == "table"
    assert block.text.splitlines()[0] == "A | 1 | 2"


@pytest.mark.parametrize(
    ("cell", "numeric"),
    [("1,234", True), ("(3,400)", True), ("$ 12.5", True), ("12%", True), ("\u2014", False),
     ("Total", False)],
)  # fmt: skip
def test_numeric_cell_regex(cell: str, numeric: bool) -> None:
    assert (_NUMERIC_RE.match(cell) is not None) is numeric


def test_table_below_four_cells_or_thirty_percent_is_layout() -> None:
    few = "<table>" + _row("alpha", "beta", "9,999") + "</table>"  # 3 non-empty cells
    assert [b.kind for b in blocks(few)] == ["text", "text", "text"]
    wordy = "<table>" + _row("a", "b", "c") + _row("d", "e", "7") + "</table>"  # 1 of 6
    assert all(b.kind != "table" for b in blocks(wordy))


def test_layout_table_yields_text_blocks() -> None:
    table = (
        "<table><tr><td><p>Left paragraph.</p></td><td><p>Right paragraph.</p></td></tr></table>"
    )
    out = blocks(table)
    assert [(b.kind, b.text) for b in out] == [
        ("text", "Left paragraph."),
        ("text", "Right paragraph."),
    ]


def test_nested_tables_outer_is_layout_inner_is_data() -> None:
    inner = "<table>" + _row("A", "1", "2") + _row("B", "3", "4") + "</table>"
    outer = f"<table><tr><td>Intro words</td><td>{inner}</td></tr></table>"
    out = blocks(outer)
    assert [b.kind for b in out] == ["text", "table"]
    assert out[1].text == "A | 1 | 2\nB | 3 | 4"


def test_caption_from_preceding_block() -> None:
    table = "<table>" + _row("A", "1", "2") + _row("B", "3", "4") + "</table>"
    out = blocks(f"<p>Net sales by segment:</p>{table}")
    assert [b.kind for b in out] == ["text", "table"]
    assert out[1].caption == "Net sales by segment:"
    # Too far back (three blocks) or too long: no caption.
    far = blocks(f"<p>Far caption</p><p>one</p><p>two</p>{table}")
    assert far[-1].caption == "two"
    none = blocks(f"<p>{'x' * 250}</p>{table}")
    assert none[-1].caption is None


# ---- rule 3: block boundaries -------------------------------------------------------


def test_double_br_splits_single_br_does_not() -> None:
    assert texts("<p>one<br>two</p>") == ["one two"]
    assert texts("<p>one<br><br>two</p>") == ["one", "two"]
    assert texts("<p>one<br> <br/>two</p>") == ["one", "two"]


def test_text_beside_block_children_gets_own_block() -> None:
    assert texts("<div>lead <p>inner</p> trail</div>") == ["lead", "inner", "trail"]


def test_list_items_and_glyph_bullets() -> None:
    out = blocks(
        "<ul><li>First</li></ul><p>\u2022 Second</p><p>- Third</p><p>(a) Fourth</p><p>1. Fifth</p>"
    )
    assert [(b.text, b.is_list_item) for b in out] == [
        ("First", True),
        ("\u2022 Second", True),
        ("- Third", True),
        ("(a) Fourth", False),
        ("1. Fifth", False),
    ]


def test_glyph_only_cell_merged_into_next_block() -> None:
    out = blocks("<table><tr><td>\u2022</td><td>The text of the bullet.</td></tr></table>")
    assert [(b.text, b.is_list_item) for b in out] == [("\u2022 The text of the bullet.", True)]


# ---- rule 4: cleanup ------------------------------------------------------------------


def test_nfkc_quotes_and_whitespace() -> None:
    out = texts("<p>\u201cHello\u201d\u00a0it\u2019s   \n  here\u2003now</p><p>   </p>")
    assert out == ['"Hello" it\'s here now']


# ---- rule 5: page furniture -----------------------------------------------------------------


def test_page_numbers_and_toc_links_removed() -> None:
    out = texts("<p>Real text.</p><p>21</p><p>Page 4 of 90</p><p>F-12</p><p>Table of Contents</p>"
                "<p>Back to Top</p><p>Index</p><p>Ends here.</p>")  # fmt: skip
    assert out == ["Real text.", "Ends here."]


def test_repeated_running_header_removed() -> None:
    footers = "".join(f"<p>Apple Inc. | 2023 Form 10-K | {n}</p><p>Body {'x' * 90} {n}.</p>"
                      for n in (19, 20, 21, 22, 23))  # fmt: skip
    out = texts(footers)
    assert len(out) == 5
    assert all(t.startswith("Body") for t in out)


def test_repeated_item_line_and_list_items_kept() -> None:
    repeated = "".join(
        "<p>Item 1A. Risk Factors</p><p>Filler paragraph here.</p>" for _ in range(5)
    )
    out = texts(repeated)
    assert out.count("Item 1A. Risk Factors") == 5
    assert out.count("Filler paragraph here.") == 0  # repeated 5 times: furniture
    bullets = "".join("<li>Same bullet</li>" for _ in range(5))
    assert texts(f"<ul>{bullets}</ul>") == ["Same bullet"] * 5


# ---- rule 6: headings --------------------------------------------------------------------------


def test_bold_short_line_is_level_3_heading() -> None:
    (b,) = blocks("<p><b>Macroeconomic Risks</b></p>")
    assert (b.kind, b.level) == ("heading", 3)
    (c,) = blocks('<div><span style="font-weight:700">Business Risks</span></div>')
    assert (c.kind, c.level) == ("heading", 3)


def test_partly_bold_line_is_text() -> None:
    (b,) = blocks("<p><b>Bold lead.</b> Then ordinary words follow.</p>")
    assert b.kind == "text"


def test_all_caps_level_2_underline_level_4() -> None:
    (a,) = blocks("<p>RISK OVERVIEW</p>")
    assert (a.kind, a.level) == ("heading", 2)
    (u,) = blocks("<p><u>Underlined heading</u></p>")
    assert (u.kind, u.level) == ("heading", 4)
    (s,) = blocks("<p>AB 12</p>")  # fewer than 3 letters
    assert s.kind == "text"


def test_item_line_is_level_1() -> None:
    (b,) = blocks("<p>Item 1A. Risk Factors</p>")
    assert (b.kind, b.level) == ("heading", 1)
    (p,) = blocks("<p>PART II</p>")
    assert (p.kind, p.level) == ("heading", 1)


def test_h_tags_are_level_2_unless_item() -> None:
    out = blocks("<h2>Overview</h2><h3>Item 7. MD&amp;A</h3>")
    assert [(b.kind, b.level) for b in out] == [("heading", 2), ("heading", 1)]


def test_long_bold_sentence_is_text() -> None:
    (b,) = blocks("<p><b>" + "word " * 40 + "</b></p>")
    assert len(b.text) > 120
    assert b.kind == "text"


# ---- input handling ---------------------------------------------------------------------------


def test_plain_text_raises() -> None:
    with pytest.raises(NotHtmlError):
        extract_blocks("ITEM 1. BUSINESS\n\nThe company makes things.\n")
    with pytest.raises(NotHtmlError):
        extract_blocks(b"plain bytes only")


def test_bytes_encoding_fallbacks_and_xml_declaration() -> None:
    latin = "<html><body><p>café</p></body></html>".encode("latin-1")
    assert texts_of(latin) == ["café"]
    utf8 = "<html><body><p>café</p></body></html>".encode()
    assert texts_of(utf8) == ["café"]
    xml = "<?xml version='1.0' encoding='ASCII'?><html><body><p>ok</p></body></html>"
    assert texts_of(xml) == ["ok"] and texts_of(xml.encode()) == ["ok"]


def texts_of(document: bytes | str) -> list[str]:
    return [b.text for b in extract_blocks(document)]


def test_deterministic_and_source_line() -> None:
    html = "<html><body>\n<p>one</p>\n<p>two</p></body></html>"
    first = extract_blocks(html)
    assert first == extract_blocks(html)
    assert [b.source_line for b in first] == [2, 3]
