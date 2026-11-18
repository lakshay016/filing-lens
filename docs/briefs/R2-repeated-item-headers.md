# R2 — repeated Item page headers in segmentation; independent source check

Read `docs/briefs/README.md` Part A, `docs/briefs/1.4-item-segmentation.md` (all; the
objective section twice), `docs/reviews/R2-pairs.md` (Microsoft section) and SPEC §5.4.

- **Branch:** `r2/repeated-item-headers` (exists; this brief is in its first commits)
- **Model:** Opus. Segmentation decides what every later comparison sees.
- **Done when:** the regression tests below pass; all four R2 filings (Apple FY2022/2023,
  Microsoft FY2022/2023) pass `scripts/check_extraction.py` with the strengthened interior
  check; the four fixture snapshots are unchanged or every change is explained; the
  Microsoft page is generated with the frozen comparison code; four repository checks pass.

## The failure (measured by the lead, Microsoft FY2023, accession 0000950170-23-035122)

Microsoft prints a bare page header `Item 1A` at the top of every Risk Factors page (15
blocks; `Item 1` likewise ~20 times). Each is a level-1 heading block and an Item
candidate. The true heading, block 343 `ITEM 1A. RISK FACTORS`, gets gain only up to the
next page header (~4,400 chars), so the DP picks the page chunk with the largest gain
(block 418). Item 1 picks block 78 over block 61 `ITEM 1. BUSINESS`. Also present: a
combined page header `Item 1B, 2, 3, 4`. Task 1.3 deliberately never removes Item-pattern
lines as page furniture, so they reach segmentation. Parse status still says `ok`.

## Fix in `parse/items.py` (do not change `html.py`)

1. **Running Item headers.** Normalise each candidate's text (NFKC, lower-case, drop
   everything that is not a letter or digit, collapse spaces). A candidate whose
   normalised text occurs **3 or more times among the document's candidates** is a
   running header. Running headers are removed from the candidate list *before* gains are
   computed, so the true heading's gain runs to the next real candidate.
2. **Fallback.** If removing running headers leaves an Item code with no candidate, but
   that code had running headers, restore the **first** running-header occurrence for
   that code as its candidate (the start of the section), and note it.
3. **Notes.** `parse_notes["running_headers"] = {normalised text: count}` and
   `parse_notes["fallback_headings"] = [codes]` (empty list when none).
4. **Paragraphs.** `Segmentation` gains `skip_blocks: frozenset[int]` (block indices of
   removed running headers). `build_paragraphs` skips them entirely: not paragraphs, not
   in `heading_path`. Only `paragraphs.py` may change for this, nothing else in it.
5. Bump `PARSER_VERSION` to `"4"`.

The table-of-contents rule, combined headings and everything else stay as in 1.4.

## Regression tests (`tests/unit/parse/test_items.py`, synthetic blocks)

- Microsoft shape: front; `ITEM 1. BUSINESS` + 20,000 chars split by 6 bare `Item 1`
  headers; `ITEM 1A. RISK FACTORS` + 40,000 chars split by 10 bare `Item 1A` headers
  where one late page chunk is the largest; then `Item 1B, 2, 3, 4` page header,
  `ITEM 1B…`, `ITEM 2…`, `ITEM 7…`, `ITEM 8…`. Expect the full-title blocks chosen, Item 1A
  `chars` ≈ 40,000 (all pages), and `running_headers` populated. **Assert the test fails
  on the current `main` code** (say so in the report).
- Only bare repeated headers exist for an Item (no full title) → fallback picks the first
  occurrence; noted in `fallback_headings`.
- A heading text that occurs twice (contents line + body) is not a running header.
- `build_paragraphs` drops skip blocks and they do not appear in any `heading_path`.

## Strengthen `scripts/check_extraction.py` (independent of the parser)

Today the raw section start is taken relative to the stored paragraphs, so a late start
still reconciles at 99%. Change it so the raw start and end do not depend on the parser:

- In the independently built raw text, find occurrences of the Item heading pattern
  (`item\s*1a\b`, case-insensitive) and of the next Item (`item\s*1b\b`). The raw section
  starts at the **earliest** Item-1A occurrence that is followed by at least 2,000
  characters before the next Item-1B occurrence, and ends at that Item-1B occurrence.
  (Contents entries are close together and do not qualify; repeated page headers inside
  the section are later than the start.)
- Repeated `Item 1A` occurrences inside the section are classified "repeated Item header".
- Text between that raw start and the first located stored paragraph is uncovered, so a
  late parser start becomes an unexplained stretch and fails.
- Add a unit test: parser output that starts at a later page header fails the interior
  check, not only the heading check.

## Run, from the main checkout (has `.env`; never print it), worktree as `--project`

```bash
uv run --project <wt> fl parse --universe <wt>/config/universes/r2_dev.toml --force
uv run --project <wt> fl parse --universe <wt>/config/universes/r2_msft.toml --force
uv run --project <wt> fl parse --universe <wt>/config/universes/demo.toml --force
uv run --project <wt> python <wt>/scripts/check_extraction.py --accession 0000320193-22-000108 --item 1A
uv run --project <wt> python <wt>/scripts/check_extraction.py --accession 0000320193-23-000106 --item 1A
uv run --project <wt> python <wt>/scripts/check_extraction.py --accession 0001564590-22-026876 --item 1A
uv run --project <wt> python <wt>/scripts/check_extraction.py --accession 0000950170-23-035122 --item 1A
```

No network; do not run `fl ingest`. If all four pass, regenerate pages with the frozen
comparison code (do not change anything under `compare/`):

```bash
uv run --project <wt> fl compare --universe <wt>/config/universes/r2_msft.toml --item 1A --out data/r2/msft-1a.html
uv run --project <wt> fl compare --universe <wt>/config/universes/r2_dev.toml --item 1A --out data/r2/apple-1a.html
uv run --project <wt> fl compare --universe <wt>/config/universes/demo.toml --item 1A --out data/demo/index.html
```

**Blinding:** do not open, read or grep the content of `data/r2/*.html`; do not compare
the two years of Apple or Microsoft in any way. For each page report only that it was
written, its byte size and `grep -c "<script"`. For XOM (the walkthrough, already
reviewed) report whether its per-pair counts changed after re-parsing; if they did, list
the paragraphs and stop for the lead. Do not touch `data/demo/index-baseline-8802f7e.html`.

## Record

In `docs/reviews/R2-pairs.md`, add "Repeated-header fix (parser v4)": the cause, the
rule, the commit, the four check results (heading, found/total, coverage, uncovered
stretches with classification), the Microsoft and Apple Item 1A section sizes before
and after (from `parse_notes`), and whether XOM's counts changed. If any filing still
fails, record it and stop; do not generate that company's page.

## Rules

README Part A. No AI attribution lines. Never fabricate a check. Quote at most 12 words
of filing text. Do not change `compare/`, `html.py`, or the frozen comparison behaviour.
