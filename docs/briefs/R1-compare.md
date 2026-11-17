# R1 — XOM demo universe, `fl compare`, baseline HTML, review note

Read `docs/briefs/README.md` Part A first. Then `docs/briefs/reader-first.md` section R1
(the goals; this brief makes steps 1 and 3–6 concrete — step 2, parser tasks 1.3–1.5, is
merged), SPEC §5 and §16 rows dated 2026-11-17.

- **Branch:** `slice1/R1-compare` (already exists; this brief is its first commit)
- **Model:** Sonnet; the lead reviews the page and the note against the SEC originals.
- **Depends on:** 1.1–1.5 merged.
- **Done when:** `uv run fl compare --universe demo --item 1A --out data/demo/index.html`
  regenerates the page from the database; the tests below pass; `docs/reviews/R1.md`
  exists with every section listed under "Review note". The HTML itself lives under
  `data/` (gitignored) and is not committed.

## Files

Create:

```
config/universes/demo.toml
src/filinglens/compare/__init__.py
src/filinglens/compare/diff.py
src/filinglens/compare/render.py
src/filinglens/compare/load.py
src/filinglens/compare/cli.py
tests/unit/compare/__init__.py
tests/unit/compare/test_diff.py
tests/unit/compare/test_render.py
tests/integration/test_compare_load.py
docs/reviews/R1.md
```

Change: `src/filinglens/cli.py` (one `add_typer` line). Nothing under `parse/` or `edgar/`.

## Step 1 — demo universe and ingest (real network, small)

```toml
# config/universes/demo.toml
name = "demo"
forms = ["10-K"]
fiscal_year_min = 2021
fiscal_year_max = 2023
store_raw = true
tickers = ["XOM"]
ciks = []
```

Run, from the main checkout (it has the `.env`; never print it):

```bash
uv run fl ingest --universe demo
uv run fl ingest --universe demo        # must print fetched 0
uv run fl parse --universe demo
uv run fl parse --universe demo --report
```

About five SEC requests in total. Record for the note: the three accessions, fiscal
periods, filing and acceptance dates (UTC), SEC primary-document URLs, the second run's
`fetched` count, and each filing's parse status and Item 1A status. Expect overall
`partial` (`short:7`, `short:8`, SPEC §17: XOM's Items 7 and 8 point to a Financial
Section) and Item 1A `ok`. If Item 1A is not `ok` in any of the three, or a fiscal year
is missing or duplicated, stop and report.

## Loading (`compare/load.py`)

```python
@dataclass(frozen=True, slots=True)
class FilingRef:
    filing_id: int; cik: int; company: str; accession: str; fiscal_year: int
    period_of_report: date; filed_date: date; accepted_at: datetime | None; url: str

@dataclass(frozen=True, slots=True)
class Para:
    seq: int; n: int                    # n = 1-based position within the Item
    heading_path: tuple[str, ...]; text: str; is_table: bool

def filings_for(session, universe: Universe) -> list[FilingRef]
    # original forms in universe.forms, fetch ok, parse ok/partial; one per fiscal_year
    # (earliest accepted_at); sorted by period_of_report
def item_paragraphs(session, filing_id: int, item: str) -> list[Para] | None
    # None when the Item's status (parse_notes) is not "ok"
```

`url` = `document_url(cik, accession, primary_document)` from `edgar.index`.

## Diff (`compare/diff.py`) — the baseline, deliberately simple

```python
OpKind = Literal["equal", "added", "removed", "replaced"]

@dataclass(frozen=True, slots=True)
class Op:
    kind: OpKind
    old: tuple[Para, ...]
    new: tuple[Para, ...]

def diff_paragraphs(old: Sequence[Para], new: Sequence[Para]) -> list[Op]
def word_diff(old_text: str, new_text: str) -> list[tuple[Literal["same", "del", "ins"], str]]
```

- Keys: `norm_exact(p.text)` (lower-case, punctuation removed; numbers kept, so an edited
  number is a change). `difflib.SequenceMatcher(None, old_keys, new_keys,
  autojunk=False).get_opcodes()`: `equal` → `equal`; `delete` → `removed`; `insert` →
  `added`; `replace` → `replaced` with **all** old and **all** new paragraphs of that
  block. Never pair paragraphs inside a `replaced` group by position.
- `word_diff` on whitespace tokens of the original text with `SequenceMatcher(autojunk=False)`;
  used only for a `replaced` op with exactly one old and one new paragraph (that pairing
  is what the matcher itself found, not a positional guess).
- A moved paragraph shows as `removed` in one place and `added` in another. That is the
  baseline's known behaviour; do not add move detection.

## Rendering (`compare/render.py`)

```python
def render_page(company: str, pairs: Sequence[PairView], generated: RunInfo) -> str
```

One self-contained HTML file: inline CSS, no JavaScript required (use `<details>`), no
external fonts, scripts or images. **Every piece of filing text goes through
`html.escape`.** Contents:

- Header: company, CIK, "Item 1A Risk Factors", generated date (UTC), commit hash,
  command, and a one-paragraph explanation of how to read the page, including: matches
  are by exact paragraph text after lower-casing and removing punctuation; a "replaced"
  group lists old and new paragraphs together and does not claim which old paragraph
  became which new one; moved text appears as removed + added.
- Per pair (FY2021→FY2022, FY2022→FY2023): fiscal years, period ends, filing dates,
  accessions, and a link to each SEC original. Counts: equal, added, removed, replaced
  groups (old/new paragraph counts).
- The ops in order. Each paragraph shows its identifier (`old ¶n` / `new ¶n`, the
  1-based position within Item 1A of that filing), its heading path when it differs
  from the previous shown paragraph, and its text. Added: green. Removed: red,
  struck through. Replaced: old block then new block in one bordered group; 1×1 groups
  also show the inline word diff. Runs of `equal` paragraphs collapse into a
  `<details>` showing "N unchanged paragraphs" (expandable to read them).
- Source location for each changed paragraph: "In the SEC original, under ‹heading›,
  search for ‹first eight words›". Use a deep link only if you verify an `id` anchor in
  the stored raw HTML that sits at that paragraph; otherwise no link (do not guess).
- Tables are shown in a `<pre>` block.

## CLI (`compare/cli.py`)

```
fl compare --universe NAME --item 1A --out PATH
```

Builds consecutive pairs from `filings_for`, skips (and prints) a pair whose Item is not
`ok` on both sides, writes the page, prints per-pair counts and the output path. Exits 1
if no pair could be built.

## Tests

`test_diff.py`: identical lists → one `equal` op; one added, one removed; a paragraph
whose only change is a number → `replaced` 1×1 (numbers are kept in the key); a moved
paragraph → one `removed` and one `added`; two consecutive edited paragraphs → one
`replaced` group with both on each side (and no positional pairing); case/punctuation
only change → `equal`; empty sides; `word_diff` on a one-word change.

`test_render.py`: a paragraph containing `<script>alert(1)</script>` and `&` renders
escaped (the raw tag never appears); unchanged runs are inside `<details>`; the SEC links
are present; ids `old ¶n` / `new ¶n` appear; no `http` reference other than `sec.gov`
links; the page contains no `<script`.

`test_compare_load.py` (`@pytest.mark.db`): synthetic filings and paragraphs → one per
fiscal year (earliest accepted wins), sorted; `item_paragraphs` returns `None` for a
`short` Item.

Section-boundary and table-of-contents behaviour are already tested in 1.4; reference
those tests in the note rather than duplicating them.

## Review note (`docs/reviews/R1.md`)

1. **Input manifest** — the step-1 table (accessions, periods, dates, URLs, statuses,
   repeat-run count).
2. **Reproduce** — the exact commands, the commit hash, and the test result line.
3. **Source checks** — for each of the three filings: the first and last Item 1A
   paragraph as extracted, and whether the same text appears in the SEC original
   (search the stored raw HTML text for it; quote at most 15 words); the heading that
   follows Item 1A; confirmation that the chosen Item 1A heading is the body one (block
   index vs the table of contents). Any omitted tables or unreadable blocks.
4. **Counts** — per pair: equal, added, removed, replaced groups.
5. **Observed baseline behaviour** — at least three concrete cases where the page shows
   something a reader could misread (for example a reworded paragraph shown as removed +
   added, a moved paragraph shown as two changes, a large replaced group, a number edit
   that is hard to spot), and at least one case the page handles well. For each: pair,
   `old ¶n` / `new ¶n`, what the page shows, what the source supports. If fewer than three
   are found, say how many and which parts were inspected.
6. **Not judged here** — state that how important each case is to a reader is left to the
   lead and author review. Do not rank them by importance.
7. **Known omissions** — Items other than 1A; XOM relocated Items 7/8 (SPEC §17); no move
   detection; no deep links unless verified.

Quote at most 15 words of filing text per example.

## Review checklist (lead)

- [ ] Open the page; follow both SEC links; check three changed paragraphs against the
      originals.
- [ ] Re-run the command from a clean shell; page regenerates identically apart from the
      timestamp.
- [ ] `grep -c "<script" data/demo/index.html` is 0.
- [ ] The note's cases are real (find each in the page and in the source).
