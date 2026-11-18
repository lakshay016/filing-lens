# R2 development pairs

Written 2026-11-17 by the implementing agent. Every statement comes from a command run
or a file read in this task. Quotes are at most 15 words. Paragraph numbers are
positions within Item 1A of that filing, as on the page.

## Pair 1: Apple Inc., FY2022 → FY2023

Universe `config/universes/r2_dev.toml` (CIK 320193, form 10-K, fiscal years 2022-2023).
Ingest: first run `new 2 | fetched 2 | skipped 0 | failed 0`; second run `new 0 |
fetched 0 | skipped 2 | failed 0`. About 4 SEC requests the first run (two submissions
pages, two documents) and 2 the second (submissions pages).

| Fiscal year | Accession | Period end | Filed | Accepted (UTC) | SEC URL |
|---|---|---|---|---|---|
| 2022 | 0000320193-22-000108 | 2022-09-24 | 2022-10-28 | 2022-10-27 22:01:14 | https://www.sec.gov/Archives/edgar/data/320193/000032019322000108/aapl-20220924.htm |
| 2023 | 0000320193-23-000106 | 2023-09-30 | 2023-11-03 | 2023-11-02 22:08:27 | https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm |

Both form 10-K. Period gap 371 days, inside the 270-460 days rule; the page has two
filings, one pair, no gap notice.

| Filing | Parse status | Item 1A status | Item 1A blocks / chars | Item 1A paragraphs |
|---|---|---|---|---|
| FY2022 | ok | ok | 118 (107 text, 11 heading) / 70,245 | 107 (0 tables) |
| FY2023 | ok | ok | 112 (100 text, 12 heading) / 67,381 | 100 (0 tables) |

Parse report (`fl parse --report`): 2 filings, 2 ok, 901 paragraphs stored in all.

### Source checks

Method: the stored raw HTML of each filing was parsed independently with `lxml`
(`text_content()`, whitespace and quotes normalised); the first 12 and last 12 words of
the first and the last Item 1A paragraph were searched in it.

| Filing | First paragraph | Last paragraph | In original |
|---|---|---|---|
| FY2022 (¶1 / ¶107) | starts "The Company's business, reputation, results of operations, financial condition and" | starts "The Company's stock has experienced substantial price volatility in the", ends "adverse impact on investor confidence and employee retention." | all four probes found, each exactly once |
| FY2023 (¶1 / ¶100) | same wording | same wording | all four probes found, each exactly once |

- The heading after Item 1A is `Item 1B. Unresolved Staff Comments` in both filings. The
  source text after the last paragraph reads Item 1B ("None.") and then Item 2 in FY2022;
  in FY2023 Item 1B, then Item 1C (Cybersecurity, "Not applicable.").
- Item 1A heading chosen at block index 125 of 745 (FY2022) and 126 of 730 (FY2023).
- Not checked: that this heading is the body heading rather than a table-of-contents
  entry (the block position is early; no separate check was made beyond the stored
  Item status); that no text between the two ends was dropped; the 107-versus-100
  paragraph difference against the original.

### Counts (`fl compare`, commit `fd6e379`)

| Pair | Unchanged | Standalone additions | Standalone removals | Changed groups (earlier / later) |
|---|---|---|---|---|
| FY2022 → FY2023 | 64 | 0 | 0 | 23 (43 / 36) |

(64 + 43 = 107 earlier and 64 + 36 = 100 later paragraphs, matching the stored counts.)
Page: `/Users/lakshay/Documents/code/filing_lens/data/r2/apple-1a.html` (gitignored);
`grep -c "<script"` prints 0. The page content was not read; no reader has seen it.

## Extraction completeness (source-only check)

Each filing is checked on its own against its own stored raw document; the two Apple
filings were not compared with each other, and neither the comparison page nor
`fl compare` output was opened or run for this check.

Command (from the main checkout, run once per accession), commit `73b5c97`:

```
uv run python scripts/check_extraction.py --accession <ACCESSION> --item 1A
```

Method: the Item 1A text is rebuilt from the raw HTML with `lxml` without the block
extractor (script, style, `ix:header` and `display:none` dropped, whitespace and quotes
normalised), cut from the body Item 1A heading to the Item 1B heading, and every stored
paragraph is located in it in order. The body heading is the last occurrence of the
heading text before the first stored paragraph. Uncovered stretches of 40 characters or
fewer are counted but not listed.

| | FY2022 (0000320193-22-000108) | FY2023 (0000320193-23-000106) |
|---|---|---|
| Heading chosen | block 125 of 745, "Item 1A. Risk Factors", section 70,245 chars | block 126 of 730, "Item 1A. Risk Factors", section 67,381 chars |
| Other blocks mentioning Item 1A | 60 (contents table), 61, 139, 337 (text, no heading) | 62 (contents table), 63, 331 (text, no heading) |
| Heading check | pass: largest section; contents entry precedes it | pass: largest section; contents entry precedes it |
| Raw section | 70,775 chars (heading occurrence 2 of 2) | 67,872 chars (heading occurrence 2 of 2) |
| Paragraphs found in order | 107 / 107 | 100 / 100 |
| Coverage | 99.24% (70,238 / 70,775) | 99.27% (67,374 / 67,872) |
| Uncovered gaps of 40 chars or fewer | 14 (407 chars) | 11 (328 chars) |
| Uncovered stretches over 40 chars | none | 1 (below) |
| Unexplained stretches | 0 | 0 |
| Result | PASS (exit 0) | PASS (exit 0) |

FY2023 stretch over 40 characters: 48 chars, classified "running header/footer, heading":
"Apple Inc. | 2023 Form 10-K | 14 Financial Risks" (the page footer followed by a
sub-heading line that no stored paragraph carries in its heading path).

Overall: PASS for both filings. Not interpreted and nothing fixed. Note: the first run
of the script left a stretch in FY2023 marked unexplained because of a bug in the
footer-pattern builder (the digit placeholder was escaped twice); it was fixed in the
committed script before the results above were taken.

## Pair 2 selected for the technical pilot: Microsoft, FY2022 → FY2023

The lead selected Microsoft with the author's approval to choose without a recruited reader. It shares Apple's fiscal-year labels and provides a second technology issuer and filing layout. Both companies are development examples. Universe: `config/universes/r2_msft.toml`, CIK 789019. Ingestion fetched two originals and fetched zero on repeat. Both received parse status `ok`.

| Fiscal year | Original filing | True body heading block | Selected block | Source-only check |
|---|---|---:|---:|---|
| 2022 | [SEC original](https://www.sec.gov/Archives/edgar/data/789019/000156459022026876/msft-10k_20220630.htm) | 350 | 405 | FAIL, selected occurrence 8 of 15 |
| 2023 | [SEC original](https://www.sec.gov/Archives/edgar/data/789019/000095017023035122/msft-20230630.htm) | 343 | 418 | FAIL, selected occurrence 11 of 15 |

In both filings the body starts at the full heading “ITEM 1A. RISK FACTORS”. Segmentation chose a later repeated “Item 1A” page heading. The interior reconciliation matched all stored paragraphs against the truncated section, illustrating why the heading and interior checks must both pass. Reproduce with `uv run python scripts/check_extraction.py --accession ACC --item 1A` for `0001564590-22-026876` and `0000950170-23-035122`.

**Decision:** Hold the Microsoft comparison page. The next engineering ticket is to fix repeated page headings during Item segmentation, cover this pattern with a regression test and rerun the source-only checks for Microsoft and Apple. Track parser provenance and regenerate affected data before building the Microsoft page. Keep the frozen comparison rules. Human references and timed sessions remain pending recruitment.

## Repeated-header fix (parser v4)

Written 2026-11-17 by the implementing agent (brief `docs/briefs/R2-repeated-item-headers.md`).

**Cause.** Microsoft prints a bare `Item 1A` page header at the top of every Risk Factors
page (14 in each filing, besides the full heading), and likewise `Item 1`, `Item 7`,
`Item 8` and `Item 15`. Each is a heading block and an Item candidate. The gain of the true
heading ran only to the next page header, so the dynamic programme chose the page whose
chunk was largest. Task 1.3 never drops Item-pattern lines as page furniture.

**Rule** (`parse/items.py`, commit `a89126f`). A candidate's text is normalised (NFKC,
lower case, every run of non-letters/digits to one space). A candidate whose normalised
text occurs 3 or more times among the document's candidates is a running header and is
removed before gains are computed. If that leaves an Item code with no candidate, one
removed occurrence for that code is restored: the first one followed by at least 2,000
characters before the next remaining candidate, or the very first if none is. This
2,000-character condition is the implementing agent's addition to the brief (see
"Decision" below). Notes: `running_headers` (text → count) and `fallback_headings`.
The removed blocks are `Segmentation.skip_blocks`. `build_paragraphs` skips them: they
are neither paragraphs nor in any heading path. `PARSER_VERSION = "4"`.

**Decision not in the brief.** Applied exactly as written, the rule broke the existing
1.4 test 3. In that test the text "Item 1A. Risk Factors" occurs three times (contents
line, body heading, stray cross-reference), so all three are running headers. The
fallback then restored the contents line and Item 1A came out `short`. The fallback now
passes over occurrences with less than 2,000 characters (`ITEM_MIN_CHARS`) before the next
remaining candidate, which is the same reasoning the gain rule uses against contents
entries. A new unit test covers this case. Test 3 is unchanged and passes.

**Strengthened check** (`scripts/check_extraction.py`, commit `a21d865`). The raw section is
now cut without the parser. Among lines starting with `item\s*1a\b` it is the earliest
followed by 2,000 or more characters before the next line starting with `item\s*1b\b`,
and it ends at that line. Text between that start and the first stored paragraph is
uncovered. Stretches made of a repeated Item pattern are classified "repeated Item
header". A unit test shows that a parser section starting at a later page header now
fails the interior check. Under the previous script that test's interior check passed.

Commands, from the main checkout, worktree as `--project`: `fl parse --force` for
`r2_dev`, `r2_msft` and `demo`, then `scripts/check_extraction.py --accession ACC --item 1A`.

| | Apple FY2022 | Apple FY2023 | Microsoft FY2022 | Microsoft FY2023 |
|---|---|---|---|---|
| Accession | 0000320193-22-000108 | 0000320193-23-000106 | 0001564590-22-026876 | 0000950170-23-035122 |
| Heading chosen | block 125 of 745 | block 126 of 730 | block 350 of 1420 | block 343 of 1366 |
| Heading check | PASS | PASS | PASS | PASS |
| Raw start | Item 1A line 2 of 2 | Item 1A line 2 of 2 | Item 1A line 2 of 16 | Item 1A line 2 of 16 |
| Paragraphs found in order | 107 / 107 | 100 / 100 | 92 / 92 | 82 / 82 |
| Coverage | 99.24% (70,238 / 70,775) | 99.27% (67,374 / 67,872) | 99.37% (69,704 / 70,144) | 99.37% (68,087 / 68,517) |
| Gaps of 40 chars or fewer | 14 (407 chars) | 11 (328 chars) | 15 (251 chars) | 15 (251 chars) |
| Stretches over 40 chars | none | 1: 48 chars, running header/footer, heading | 1: 66 chars, heading | 1: 66 chars, heading |
| Unexplained | 0 | 0 | 0 | 0 |
| Result | PASS (exit 0) | PASS (exit 0) | PASS (exit 0) | PASS (exit 0) |

For Microsoft, raw line occurrence 2 is the bare `Item 1A` page header at the top of the
first Risk Factors page (block 349, directly before the full heading at block 350).
The full heading then falls in a gap of 40 characters or fewer. The 66-character stretch
in each Microsoft filing is a sub-heading line that no stored paragraph carries in its
heading path.

Item 1A section sizes from `parse_notes` (the comparison between years was not looked at):

| Filing | Before (v3): chars / blocks / paragraphs | After (v4): chars / blocks / paragraphs | `running_headers` (v4) |
|---|---|---|---|
| Apple FY2022 | 70,245 / 118 / 107 | 70,245 / 118 / 107 | none |
| Apple FY2023 | 67,381 / 112 / 100 | 67,381 / 112 / 100 | none |
| Microsoft FY2022 | 41,678 / 67 / 54 | 69,870 / 122 / 92 | item 1: 20, item 1a: 14, item 7: 16, item 8: 42, item 15: 6 |
| Microsoft FY2023 | 23,738 / 37 / 30 | 68,253 / 112 / 82 | item 1: 20, item 1a: 14, item 7: 17, item 8: 41, item 15: 6 |

`fallback_headings` is empty for all four, and for the three Exxon filings, which have no
running headers.

**Exxon.** After re-parsing, the per-pair counts are unchanged: FY2021 → FY2022 unchanged 16,
changed groups 8 (24 / 22), FY2022 → FY2023 unchanged 14, changed groups 11 (24 / 25),
no standalone additions or removals. This matches the run before re-parsing. All 2,344
stored Exxon paragraphs are also identical in item, seq, exact hash and heading path.

**Fixture snapshots** (`tests/snapshots/items_*.json`, `paragraphs_*.json`): unchanged.

**Pages** (frozen comparison code; Apple and Microsoft stdout discarded, content not read):
`data/r2/msft-1a.html` 159,899 bytes, `data/r2/apple-1a.html` 164,646 bytes,
`data/demo/index.html` 145,672 bytes. `grep -c "<script"` prints 0 for each.
