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

## Second pair: chosen by the author from the reader's coverage

Placeholder. To add it:

1. The author names the company (the one the reader's coverage selects).
2. Add its CIK to `ciks` in `config/universes/r2_dev.toml`, keeping 320193; widen
   `fiscal_year_min` / `fiscal_year_max` if the pair needs other years.
3. Run `fl ingest` twice (the second must fetch 0), `fl parse`, `fl parse --report`, then
   `fl compare --universe config/universes/r2_dev.toml --item 1A --out data/r2/<name>-1a.html`.
4. Record accessions, periods, filing dates, URLs, parse and Item 1A status, the source
   checks and the counts here, in the same form as the Apple pair.
