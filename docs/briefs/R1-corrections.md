# R1 corrections before R2, and the Apple development pair

Read `docs/briefs/README.md` Part A first. Then `docs/briefs/R1-compare.md` (the merged
baseline), `docs/reviews/R1.md`, `TODO.md` ("Before timed R2 sessions"), SPEC §6.1 and the
§16 row dated 2026-11-17 that starts "R1 baseline accepted for development".

- **Branch:** `slice1/R1-corrections` (already exists; this brief is in its first commit)
- **Model:** Sonnet; the lead checks each acceptance case on the regenerated pages.
- **Depends on:** PR #14 (R1 baseline) merged.
- **Done when:** the three corrections below pass their tests; the XOM page is regenerated
  and the before/after section of `docs/reviews/R1.md` is filled; the Apple FY2022→2023
  page is generated and its section checks recorded; the four repository checks pass.

The baseline page is preserved by the lead at `data/demo/index-baseline-8802f7e.html`.
Do not overwrite or delete it. Matching beyond these corrections stays frozen (no move
detection, no similarity matching): reader sessions must see a stable method.

## Files

Change: `src/filinglens/compare/{diff,render,load,cli}.py`, `tests/unit/compare/*`,
`tests/integration/test_compare_load.py`, `docs/reviews/R1.md`. Create:
`config/universes/r2_dev.toml`, `docs/reviews/R2-pairs.md`. Nothing else.

## Correction 1 — a comparison key that keeps meaning

Replace `norm_exact` as the paragraph key in `compare/diff.py` with a new function in the
same module:

```python
def compare_key(text: str) -> str
    # NFKC; lower-case; curly quotes and apostrophes -> straight; every run of Unicode
    # whitespace (incl. non-breaking) -> one space; strip. Nothing else is removed:
    # punctuation, signs, brackets, currency symbols, %, <, >, ≤, ≥ all stay.
```

`norm_exact` itself is unchanged (the aligner and hashes depend on it).

Acceptance tests (`test_diff.py`), each asserting `compare_key(a) == compare_key(b)` or not:

| a | b | equal? |
|---|---|---|
| `Net income increased 5% to $1.2 billion.` | `Net income decreased (5%) to $1.2 billion.` | no |
| `a change of 5%` | `a change of -5%` | no |
| `a loss of (3,400)` | `a loss of 3,400` | no |
| `$5 million` | `€5 million` | no |
| `less than 10%` → `<10%` vs `>10%` | | no |
| `Risk   relating to\n China.` | `Risk relating to China.` | yes |
| `It’s “material”.` | `It's "material".` | yes |
| `RISK FACTORS` | `Risk Factors` | yes |

Also: `diff_paragraphs` on old `[p, "loss of (3,400)"]` / new `[p, "loss of 3,400"]` gives
`equal` then a 1×1 `replaced`.

## Correction 2 — §6.1 eligibility before building a pair

In `compare/load.py` add:

```python
@dataclass(frozen=True, slots=True)
class Gap:
    old: FilingRef; new: FilingRef; reason: str      # e.g. "period gap 731 days; FY2022 filing missing"

def plan_pairs(filings: Sequence[FilingRef]) -> list[tuple[FilingRef, FilingRef] | Gap]
```

Consecutive filings of one company (already one per fiscal year, sorted) form a pair only
when SPEC §6.1 holds: same CIK, both original 10-Ks (forms `10-K`/`10-K405`), and
`270 <= (new.period_of_report - old.period_of_report).days <= 460`. Otherwise emit a
`Gap` with the reason, naming the missing fiscal year(s) when the gap is over 460 days.
The CLI prints each gap; the page shows each gap in order as a visible notice ("No
comparison: …") and never shows an annual comparison across it. Exit 1 only when there is
neither a pair nor a gap.

Tests: FY2021, FY2023 (FY2022 missing) → one `Gap`, no pair; FY2021, FY2022, FY2023 →
two pairs; periods 200 days apart → `Gap`; the page for the missing-year case contains
the notice and no comparison block.

## Correction 3 — honest counts and neutral unresolved groups

- Counts table columns become: `Unchanged`, `Standalone additions`, `Standalone
  removals`, `Changed groups (earlier / later paragraphs)`. Directly under it, one line:
  "Changed groups can contain new or removed passages; read each group."
- A `replaced` op with exactly one paragraph on each side keeps today's display: earlier
  and later paragraphs plus the inline word diff.
- Any other `replaced` op is **unresolved**: show the earlier paragraphs under a label
  "Earlier filing" and the later ones under "Later filing", in one bordered group, in
  neutral styling: no strikethrough, no red or green fill, normal readable text. The
  group label says "Changed group: N earlier / M later paragraphs; not matched paragraph
  by paragraph".
- Standalone `added` / `removed` ops keep their colours; removed text may stay struck
  through.
- Update the page's "how to read" paragraph to match.

Tests (`test_render.py`): unresolved group HTML has no `line-through` class or style and
no added/removed class; a 1×1 group still has the word-diff block; counts headers read as
above; the explanatory line is present.

Verification on the real page (record in the note): FY2022→2023 later ¶16 (the new bullet
found in R1 case D) is shown as readable later-filing text inside an unresolved group,
not struck through; FY2022→2023 ¶12 (the R1 control, an added phrase in a 1×1 group)
still shows its inline addition.

## Regenerate XOM and update the note

From the main checkout (it has `.env`; never print it), with your worktree as `--project`:

```bash
uv run --project <worktree> fl compare --universe <worktree>/config/universes/demo.toml --item 1A --out data/demo/index.html
```

In `docs/reviews/R1.md` add a section "Corrections (pre-R2)": the commit; per-pair counts
before (from the note) and after; every paragraph whose op changed because of the new key
(old/new ¶, before → after); the two verification checks above. If any count changed,
say exactly which paragraphs and why (the lead escalates a substantive change to the
author).

## Apple development pair

`config/universes/r2_dev.toml`:

```toml
name = "r2_dev"
forms = ["10-K"]
fiscal_year_min = 2022
fiscal_year_max = 2023
store_raw = true
tickers = []
ciks = [320193]        # Apple Inc.; explicit CIK (ticker maps can change, see R1)
```

Ingest (twice; second must fetch 0), parse, report, then
`fl compare --universe <path> --item 1A --out data/r2/apple-1a.html`. About three SEC
requests. Record in `docs/reviews/R2-pairs.md`: accessions, periods, filing dates, SEC
URLs, parse and Item 1A status, first and last Item 1A paragraph checked against the
stored original (quote at most 15 words), the heading after Item 1A, per-pair counts.
Leave a placeholder section "Second pair — chosen by the author from the reader's
coverage" with the steps to add it (a second CIK in `r2_dev.toml`, rerun). Do not open
the Apple page's content to any reader; the independent reference list is made from the
originals first (author's task).

## Rules

As README Part A. No AI attribution lines. Never fabricate a check; say what was not
checked. Quote at most 15 words of filing text per example.
