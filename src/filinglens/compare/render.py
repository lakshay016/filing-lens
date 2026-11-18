"""Render the baseline comparison as one self-contained static HTML page (brief R1).

No JavaScript, no external resources. Every piece of text that came from a filing, and
every value that came from the database, goes through ``html.escape``.
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from filinglens.compare.diff import Op, word_diff
from filinglens.compare.load import FilingRef, Gap, Para


@dataclass(frozen=True, slots=True)
class PairView:
    old: FilingRef
    new: FilingRef
    ops: Sequence[Op]


@dataclass(frozen=True, slots=True)
class RunInfo:
    generated: datetime
    commit: str
    command: str


@dataclass(frozen=True, slots=True)
class PairCounts:
    equal: int  # paragraphs
    added: int  # paragraphs
    removed: int  # paragraphs
    replaced_groups: int  # changed groups
    replaced_old: int  # earlier-filing paragraphs in all changed groups
    replaced_new: int  # later-filing paragraphs in all changed groups


def pair_counts(ops: Sequence[Op]) -> PairCounts:
    return PairCounts(
        equal=sum(len(o.new) for o in ops if o.kind == "equal"),
        added=sum(len(o.new) for o in ops if o.kind == "added"),
        removed=sum(len(o.old) for o in ops if o.kind == "removed"),
        replaced_groups=sum(1 for o in ops if o.kind == "replaced"),
        replaced_old=sum(len(o.old) for o in ops if o.kind == "replaced"),
        replaced_new=sum(len(o.new) for o in ops if o.kind == "replaced"),
    )


_CSS = """
:root{--fg:#1d2330;--muted:#5b6475;--bg:#fff;--line:#d5d9e0;--add:#e6f4ea;--add-b:#2e7d32;
--del:#fdecea;--del-b:#c62828;--rep:#f5f6f8}
@media (prefers-color-scheme:dark){:root{--fg:#e4e7ee;--muted:#9aa3b5;--bg:#14171f;--line:#343a49;
--add:#16301d;--add-b:#66bb6a;--del:#38191a;--del-b:#ef7a73;--rep:#1c202b}}
body{font:16px/1.5 Georgia,serif;color:var(--fg);background:var(--bg);margin:0 auto;
max-width:62rem;padding:1rem 16px 4rem}
h1{font-size:1.5rem;margin:.5rem 0}h2{font-size:1.25rem;margin:2.5rem 0 .5rem;
border-top:2px solid var(--line);padding-top:1rem}
.meta,.src,.pid{font:13px/1.4 system-ui,sans-serif;color:var(--muted)}
.how{font:14px/1.45 system-ui,sans-serif;background:var(--rep);border:1px solid var(--line);
padding:.1rem .9rem;margin:1rem 0}
a{color:inherit}
table.counts{border-collapse:collapse;font:14px system-ui,sans-serif;margin:.5rem 0 1rem}
table.counts td,table.counts th{border:1px solid var(--line);padding:.2rem .6rem;text-align:left}
.heading{font:600 13px system-ui,sans-serif;color:var(--muted);margin:1rem 0 .2rem}
.para{margin:.4rem 0;padding:.4rem .7rem;border-left:4px solid var(--line);overflow-wrap:anywhere}
.para.added{background:var(--add);border-left-color:var(--add-b)}
.para.removed{background:var(--del);border-left-color:var(--del-b)}
.para.removed .text{text-decoration:line-through}
.group{border:2px solid var(--line);margin:.8rem 0;padding:.3rem .6rem;background:var(--rep)}
.group .label{font:600 12px system-ui,sans-serif;text-transform:uppercase;color:var(--muted)}
ins{background:var(--add);color:inherit;text-decoration:underline}
del{background:var(--del);color:inherit}
details{margin:.6rem 0}summary{cursor:pointer;font:14px system-ui,sans-serif;color:var(--muted)}
pre{white-space:pre-wrap;font:13px/1.4 ui-monospace,monospace;margin:.2rem 0}
.para.neutral{background:var(--rep)}
.group h4{font:600 13px system-ui,sans-serif;margin:.6rem 0 .1rem}
.gap{border:2px dashed var(--line);margin:1rem 0;padding:.6rem .9rem;
font:14px system-ui,sans-serif;background:var(--rep)}
.note{font:13px system-ui,sans-serif;color:var(--muted);margin:.2rem 0 1rem}
.where{margin-top:.2rem}
@media (max-width:600px){body{font-size:15px}}
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _first_words(text: str, n: int = 8) -> str:
    return " ".join(text.split()[:n])


def _span(paras: Sequence[Para], side: str) -> str:
    first, last = paras[0].n, paras[-1].n
    return f"{side} ¶{first}" if first == last else f"{side} ¶{first}-{last}"


class _Headings:
    """Tracks the last heading shown so a heading is printed only when it changes."""

    def __init__(self) -> None:
        self.last: tuple[str, ...] | None = None

    def show(self, para: Para) -> str:
        if para.heading_path == self.last:
            return ""
        self.last = para.heading_path
        label = " / ".join(para.heading_path) if para.heading_path else "(no heading)"
        return f'<div class="heading">{_e(label)}</div>'


def _body(para: Para) -> str:
    if para.is_table:
        return f'<pre class="text">{_e(para.text)}</pre>'
    return f'<div class="text">{_e(para.text)}</div>'


def _where(para: Para, item_label: str) -> str:
    heading = para.heading_path[-1] if para.heading_path else item_label
    return (
        '<div class="src where">In the SEC original, under '
        f"&lsquo;{_e(heading)}&rsquo;, search for "
        f"&lsquo;{_e(_first_words(para.text))}&rsquo;</div>"
    )


def _para_html(para: Para, side: str, kind: str, headings: _Headings, item_label: str) -> str:
    return (
        headings.show(para)
        + f'<div class="para {kind}"><div class="pid">{_e(side)} ¶{para.n}</div>'
        + _body(para)
        + _where(para, item_label)
        + "</div>"
    )


def _equal_html(op: Op, headings: _Headings) -> str:
    n = len(op.new)
    noun = "paragraph" if n == 1 else "paragraphs"
    summary = f"{n} unchanged {noun} ({_span(op.old, 'old')}, {_span(op.new, 'new')})"
    inner = "".join(
        headings.show(new) + f'<div class="para"><div class="pid">{_e(_span([old], "old"))} = '
        f"{_e(_span([new], 'new'))}</div>{_body(new)}</div>"
        for old, new in zip(op.old, op.new, strict=True)
    )
    return f"<details><summary>{_e(summary)}</summary>{inner}</details>"


def _word_diff_html(old: Para, new: Para) -> str:
    parts: list[str] = []
    for kind, words in word_diff(old.text, new.text):
        if kind == "same":
            parts.append(_e(words))
        elif kind == "del":
            parts.append(f"<del>{_e(words)}</del>")
        else:
            parts.append(f"<ins>{_e(words)}</ins>")
    return (
        '<div class="para"><div class="pid">word differences, old → new</div>'
        f'<div class="text">{" ".join(parts)}</div></div>'
    )


def _replaced_html(op: Op, headings: _Headings, item_label: str) -> str:
    if len(op.old) == 1 and len(op.new) == 1:
        label = "Changed: 1 earlier / 1 later paragraph, with a word-level difference."
        olds = _para_html(op.old[0], "old", "removed", headings, item_label)
        news = _para_html(op.new[0], "new", "added", headings, item_label)
        extra = _word_diff_html(op.old[0], op.new[0])
        return f'<div class="group"><div class="label">{_e(label)}</div>{olds}{news}{extra}</div>'
    label = (
        f"Changed group: {len(op.old)} earlier / {len(op.new)} later paragraphs; "
        "not matched paragraph by paragraph"
    )
    olds = "".join(_para_html(p, "old", "neutral", headings, item_label) for p in op.old)
    news = "".join(_para_html(p, "new", "neutral", headings, item_label) for p in op.new)
    return (
        f'<div class="group"><div class="label">{_e(label)}</div>'
        f"<h4>Earlier filing</h4>{olds}<h4>Later filing</h4>{news}</div>"
    )


def _gap_html(gap: Gap) -> str:
    text = f"No comparison: FY{gap.old.fiscal_year} \u2192 FY{gap.new.fiscal_year} ({gap.reason})."
    return f'<div class="gap">{_e(text)}</div>'


def _filing_line(ref: FilingRef, side: str) -> str:
    accepted = ref.accepted_at.strftime("%Y-%m-%d %H:%M UTC") if ref.accepted_at else "unknown"
    return (
        f"<tr><th>{_e(side)}</th><td>FY{_e(ref.fiscal_year)}</td>"
        f"<td>{_e(ref.period_of_report)}</td><td>{_e(ref.filed_date)}</td>"
        f"<td>{_e(accepted)}</td><td>{_e(ref.accession)}</td>"
        f'<td><a href="{_e(ref.url)}">SEC original</a></td></tr>'
    )


def _pair_html(pair: PairView, item_label: str) -> str:
    counts = pair_counts(pair.ops)
    title = f"FY{pair.old.fiscal_year} → FY{pair.new.fiscal_year}"
    parts = [
        f"<h2>{_e(title)}</h2>",
        '<table class="counts"><tr><th></th><th>Fiscal year</th><th>Period end</th>'
        "<th>Filed</th><th>Accepted</th><th>Accession</th><th>Source</th></tr>",
        _filing_line(pair.old, "old"),
        _filing_line(pair.new, "new"),
        "</table>",
        '<table class="counts"><tr><th>Unchanged</th><th>Standalone additions</th>'
        "<th>Standalone removals</th>"
        "<th>Changed groups (earlier / later paragraphs)</th></tr>"
        f"<tr><td>{counts.equal} paragraphs</td><td>{counts.added} paragraphs</td>"
        f"<td>{counts.removed} paragraphs</td>"
        f"<td>{counts.replaced_groups} (earlier {counts.replaced_old} / later "
        f"{counts.replaced_new} paragraphs)</td></tr></table>",
        '<p class="note">Changed groups can contain new or removed passages; read each group.</p>',
    ]
    headings = _Headings()
    for op in pair.ops:
        if op.kind == "equal":
            parts.append(_equal_html(op, headings))
        elif op.kind == "added":
            parts.extend(_para_html(p, "new", "added", headings, item_label) for p in op.new)
        elif op.kind == "removed":
            parts.extend(_para_html(p, "old", "removed", headings, item_label) for p in op.old)
        else:
            parts.append(_replaced_html(op, headings, item_label))
    return "\n".join(parts)


_HOW = (
    "<p><b>How to read this page.</b> Each filing's Item is split into paragraphs, numbered "
    "from 1 in filing order (old ¶n and new ¶n are positions within that Item of "
    "that filing). Two paragraphs count as the same when their text is identical after "
    "lower-casing, straightening quotes and collapsing spaces; punctuation, signs, "
    "brackets, currency symbols and numbers are kept, so an edited number or sign is a "
    "change. Green paragraphs are standalone additions and red struck-through paragraphs "
    "are standalone removals. A <em>changed group</em> is a stretch where the two filings "
    "differ: when it holds one earlier and one later paragraph they are shown with a "
    "word-level difference; otherwise the earlier-filing and later-filing paragraphs are "
    "listed side by side in plain text, without colours, because the page does not claim "
    "which earlier paragraph became which later one, and a group can contain new or "
    "removed passages. Text that moved appears twice: removed in one place and added in "
    "another. Unchanged runs are folded; open them for context. Where a year is missing "
    "or the periods are not about a year apart, a notice replaces the comparison. This is "
    "a baseline, not a judgment of which changes matter.</p>"
)


def render_page(
    company: str,
    pairs: Sequence[PairView | Gap],
    generated: RunInfo,
    item_title: str = "Item 1A Risk Factors",
) -> str:
    cik = pairs[0].new.cik if pairs else ""
    item_label = " ".join(item_title.split()[:2])
    meta = (
        f"CIK {_e(cik)} · generated {_e(generated.generated.strftime('%Y-%m-%d %H:%M UTC'))} "
        f"· commit {_e(generated.commit)} · <code>{_e(generated.command)}</code>"
    )
    body = "\n".join(
        _gap_html(p) if isinstance(p, Gap) else _pair_html(p, item_label) for p in pairs
    )
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(company)} {_e(item_title)}, baseline comparison</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<h1>{_e(company)} — {_e(item_title)}</h1>"
        f'<div class="meta">{meta}</div>'
        f'<div class="how">{_HOW}</div>'
        f"{body}</body></html>\n"
    )
