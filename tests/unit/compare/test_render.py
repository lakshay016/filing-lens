from __future__ import annotations

import re
from datetime import UTC, date, datetime

from filinglens.compare.diff import diff_paragraphs
from filinglens.compare.load import FilingRef, Gap, Para
from filinglens.compare.render import PairView, RunInfo, render_page


def ref(year: int, accession: str) -> FilingRef:
    return FilingRef(
        filing_id=year,
        cik=1,
        company="Acme <Corp> & Co",
        accession=accession,
        fiscal_year=year,
        period_of_report=date(year, 12, 31),
        filed_date=date(year + 1, 2, 20),
        accepted_at=datetime(year + 1, 2, 20, 21, 0, tzinfo=UTC),
        url=f"https://www.sec.gov/Archives/edgar/data/1/{accession.replace('-', '')}/doc.htm",
    )


def paras(*texts: str, table: bool = False) -> list[Para]:
    return [
        Para(seq=i, n=i + 1, heading_path=("Risks",), text=t, is_table=table)
        for i, t in enumerate(texts)
    ]


def page() -> str:
    old = paras("same one", "same two", "Old <b>text</b> & more", "tail")
    new = paras("same one", "same two", "<script>alert(1)</script> & new", "tail")
    pair = PairView(
        ref(2021, "0000000001-22-000001"),
        ref(2022, "0000000001-23-000002"),
        diff_paragraphs(old, new),
    )
    info = RunInfo(datetime(2026, 11, 17, tzinfo=UTC), "abc1234", "uv run fl compare <x>")
    return render_page("Acme <Corp> & Co", [pair], info)


def test_filing_text_is_escaped() -> None:
    html = page()
    assert "<script" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; new" in html
    assert "Old &lt;b&gt;text&lt;/b&gt; &amp; more" in html
    assert "Acme &lt;Corp&gt; &amp; Co" in html


def test_unchanged_run_is_in_details() -> None:
    html = page()
    assert "<details><summary>2 unchanged paragraphs" in html
    assert "same one" in html.split("<details>")[1].split("</details>")[0]


def test_sec_links_and_paragraph_ids() -> None:
    html = page()
    assert html.count('href="https://www.sec.gov/Archives/edgar/data/1/') == 2
    assert "old ¶3" in html and "new ¶3" in html


def test_only_sec_gov_references_and_no_script() -> None:
    html = page()
    urls = re.findall(r"https?://[^\s\"'<>]+", html)
    assert urls and all(u.startswith("https://www.sec.gov/") for u in urls)
    assert "<script" not in html and "<link" not in html and "<img" not in html


def test_table_is_preformatted() -> None:
    pair = PairView(
        ref(2021, "0000000001-22-000001"),
        ref(2022, "0000000001-23-000002"),
        diff_paragraphs([], paras("a | b", table=True)),
    )
    html = render_page("Acme", [pair], RunInfo(datetime(2026, 1, 1, tzinfo=UTC), "x", "y"))
    assert '<pre class="text">a | b</pre>' in html


def render_ops(old: list[Para], new: list[Para]) -> str:
    pair = PairView(
        ref(2021, "0000000001-22-000001"),
        ref(2022, "0000000001-23-000002"),
        diff_paragraphs(old, new),
    )
    return render_page("Acme", [pair], RunInfo(datetime(2026, 1, 1, tzinfo=UTC), "x", "y"))


def group_html(html: str) -> str:
    return html.split('<div class="group">')[1].split("</div></div>\n")[0]


def test_unresolved_group_is_neutral() -> None:
    html = render_ops(paras("o1", "o2", "o3"), paras("n1", "n2"))
    group = group_html(html)
    assert "Changed group: 3 earlier / 2 later paragraphs; not matched paragraph by paragraph" in (
        html
    )
    assert "Earlier filing" in group and "Later filing" in group
    assert "line-through" not in group
    assert not re.search(r'class="[^"]*\b(added|removed)\b', group)
    assert "word differences" not in group
    assert all(t in group for t in ("o1", "o2", "o3", "n1", "n2"))


def test_one_by_one_group_keeps_word_diff() -> None:
    html = render_ops(paras("the risk is high"), paras("the risk is low"))
    assert "word differences" in html
    assert "<del>high</del>" in html and "<ins>low</ins>" in html


def test_counts_headers_and_explanation() -> None:
    html = page()
    for header in (
        "<th>Unchanged</th>",
        "<th>Standalone additions</th>",
        "<th>Standalone removals</th>",
        "<th>Changed groups (earlier / later paragraphs)</th>",
    ):
        assert header in html
    assert "Changed groups can contain new or removed passages; read each group." in html


def test_standalone_ops_keep_colours() -> None:
    html = render_ops(paras("a", "b"), paras("a"))
    assert 'class="para removed"' in html


def test_gap_notice_and_no_comparison_block() -> None:
    old, new = ref(2021, "0000000001-22-000001"), ref(2023, "0000000001-24-000003")
    gap = Gap(old, new, "period gap 730 days; FY2022 filing missing")
    html = render_page("Acme", [gap], RunInfo(datetime(2026, 1, 1, tzinfo=UTC), "x", "y"))
    assert "No comparison: FY2021 → FY2023 (period gap 730 days; FY2022 filing missing)." in html
    assert '<div class="group">' not in html and '<table class="counts"' not in html
