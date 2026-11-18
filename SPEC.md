# Filing Lens — Build Specification

Revision 2026-11-17 · Ingestion implementation merged · Reader-first delivery plan

This is the single source of truth for building Filing Lens. It is written so that an
implementer (a person or a coding model) who was not part of the design discussion can
build the project from it without re-deciding anything.

**Related documents:** [docs/PRODUCT.md](docs/PRODUCT.md) (what the product is, its
restrictions and limitations), [docs/STATUS.md](docs/STATUS.md) (current progress),
[CLAUDE.md](CLAUDE.md) (rules for agents), [TODO.md](TODO.md) (task checklist).

**How to read it**

- Statements are decisions unless tagged otherwise. Do not re-litigate them; if one turns
  out to be wrong, record the change in §16 (Decision log) with the reason.
- `[VERIFY]` marks a fact recalled from memory that must be checked against the primary
  source (paper, vendor docs, terms of use) before code depends on it.
- `[OPEN]` marks a decision that is deliberately deferred, with a default to use until
  it is resolved.
- `[EXPANSION]` marks work that is designed for but not built in the current slices.
- Build in the order of §14. Sections 5–11 describe candidate components. Schedule them only when the corresponding review selects them.

---

## 1. What this is

Filing Lens is a change-aware research tool over SEC filings. One core engine aligns a
company's consecutive annual reports paragraph by paragraph. Everything else is built on
that alignment:

1. **Change alerts** — when a held company files, show the substantive changes versus
   last year, each linked to the exact paragraph.
2. **Temporal RAG** — question answering over a *versioned* index in which a paragraph
   that did not change for five years is stored once, with the years it was valid.
3. **Research** — the same alignment scores are the text-change signal from the
   "Lazy Prices" paper, tested against stock returns once survivorship-bias-free price
   data is available.

### 1.1 Goals

- A solo-owned project that replaces course projects on the resume.
- Technical depth in one place (the alignment engine and the retrieval built on it),
  not breadth across many frameworks.
- Every number on the resume comes from a measured, reproducible run.
- Running cost of $0 by default.
- Useful to the author: it watches the author's own holdings.

### 1.2 Non-goals

- No buy/sell recommendations, trading, or personalised investment advice. Backtest
  output is research.
- No LangGraph or other agent framework; orchestration is a hand-written state machine.
- No LLM-extracted knowledge graph, no fine-tuning, no multi-agent report writer.
- No Canadian 40-F filers in the current slices.

### 1.3 Why it is not "basic RAG"

Naive RAG over multi-year filings has a specific failure: near-identical paragraphs
from each year are all indexed, retrieval returns several copies, and the model mixes
up years. The versioned index (§8.1) removes that failure by construction, and the
ablation ladder (§9.4) measures how much each added component is worth. A component
that does not improve the measured result is removed and the removal is written up.

---

## 2. Hard constraints

Any change to the plan must still satisfy all of these.

### 2.1 Cost

- Default budget $0. Any paid API account has a hard monthly cap ($20).
- No frontier model is used as a runtime model. Runtime models are free-tier or local.
- All LLM responses are cached on disk during development (§10.3).
- The public demo has per-IP and global daily query caps and serves cached answers
  for its example questions.

### 2.2 SEC EDGAR fair access

- Every request sends a `User-Agent` with a name and contact email, read from
  `FL_SEC_USER_AGENT`. The app refuses to start a fetch if it is unset.
- Stay under the SEC limit of 10 requests/second; the fetcher is capped at 8/s globally.
- Back off on HTTP 429 and 403; never retry in a tight loop.

### 2.3 WRDS / CRSP (applies from the moment access is granted)

1. Academic, non-commercial use only. CRSP is used only for the offline Lazy Prices
   backtest. It never feeds the watcher, the deployed app, or personal trading.
2. No redistribution or display. Raw CRSP data never goes into the repo, the deployed
   database, logs, screenshots, or any public place. Only code, method, and aggregate
   results are published.
3. **The CIK-to-PERMNO link table is licensed data too** and is treated identically.
4. No CRSP data, and nothing row-level derived from it, is sent to any LLM. This
   includes coding assistants: no AI session is run with licensed files readable.
   The assistant writes code against the schema in §11.6 and synthetic fixtures; the
   author runs it.
5. Access only through the official `wrds` Python package or WRDS Cloud.
6. Credentials live in the user-level `~/.pgpass` created by the `wrds` package, never
   in the repo or `.env`.
7. Licensed data lives outside the repo at `FL_LICENSED_DIR` (default
   `~/filinglens-licensed/`), not in a cloud-synced folder.
8. Cite WRDS and CRSP in the README and write-up using the wording from the WRDS Terms
   of Use. `[VERIFY]` exact wording when access is granted.
9. Before publishing anything derived from CRSP, get written confirmation from the
   UofT library that a public portfolio write-up with aggregate results is permitted.

### 2.4 Other data

- FinanceBench open set (150 questions) is for non-commercial use. It is downloaded by
  script and not committed to the repo. Licence on the dataset card: CC BY-NC 4.0
  (verified 2026-11-15, §16).
- Free-tier LLM providers may use prompts to improve their products. Only public filing
  text goes to them. Anything that reveals the author's holdings goes only through a
  provider tagged `private_ok` in config, or a local model (§10.2).

---

## 3. Architecture

```
                       OFFLINE (laptop)                         ONLINE (free hosts)
 ┌─────────┐   ┌────────┐   ┌───────────┐   ┌────────────┐
 │ EDGAR   │──▶│ ingest │──▶│  parse    │──▶│  align     │──┬─▶ change classifier ─▶ alerts
 │ (public)│   │ fetch  │   │ items +   │   │ paragraph  │  │
 └─────────┘   └────────┘   │ paragraphs│   │ alignment  │  ├─▶ versioned index ─▶ hybrid retrieval
                            └───────────┘   └────────────┘  │        (Postgres+pgvector)   │
 ┌─────────┐                                                │                              ▼
 │ XBRL    │──▶ fact table ─────────────────────────────────┼──────────────▶ router ─▶ generate ─▶ verify
 │ facts   │                                                │                                     │
 └─────────┘                                                │                              FastAPI + Next.js
                                                            └─▶ similarity signal (Parquet)
 ┌──────────────┐                                                       │
 │ PriceSource  │  synthetic │ free │ CRSP [EXPANSION] ───────▶ backtest engine ─▶ aggregate results
 └──────────────┘
```

Two storage tiers, on purpose:

| Tier | Holds | Where | Why |
|---|---|---|---|
| App | RAG universe (about 40–60 companies): paragraphs, versions, embeddings, facts, alerts, traces | PostgreSQL + pgvector (Docker locally, free host when deployed) | Small enough for a free hosted database |
| Bulk | Backtest universe (thousands of companies): extracted text, similarity signals, returns | Parquet files under `data/`, queried with DuckDB | Too big for a free hosted database; never needs to be online |

### 3.1 Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 (machine currently has 3.11.9; install 3.12 via `uv`) |
| Packaging | `uv`, `pyproject.toml`, `src/` layout |
| API | FastAPI, async SQLAlchemy 2, Alembic |
| App database | PostgreSQL 16 + pgvector |
| Bulk analytics | DuckDB + Parquet, pandas, NumPy, SciPy sparse |
| HTTP | `httpx` (async) |
| HTML parsing | `lxml` (fast, tolerant); `selectolax` is an acceptable swap |
| ML | scikit-learn (TF-IDF, baselines), own NumPy softmax, `sentence-transformers` / ONNX Runtime for local embedding, rerank and NLI models |
| CLI | `typer`, entry point `fl` |
| Tests | `pytest`, `pytest-asyncio`, `hypothesis` for the aligner |
| Lint/format/type | `ruff`, `mypy` on `src/filinglens/align` and `backtest` at minimum |
| Frontend (slice 2) | Next.js + TypeScript |
| CI | GitHub Actions |

### 3.2 Repository layout

```
filing_lens/
├── SPEC.md                    this file
├── README.md
├── pyproject.toml
├── docker-compose.yml         local Postgres + pgvector
├── .env.example               variable names only, no values
├── config/
│   ├── universes/             t0_dev.toml, t1_rag.toml, t2_backtest.toml
│   ├── models.toml            provider + model ids, privacy tags (§10)
│   └── concepts.toml          metric -> candidate XBRL tags (§8.5)
├── src/filinglens/
│   ├── edgar/                 client.py, index.py, fetch.py, xbrl.py
│   ├── parse/                 html.py, items.py, paragraphs.py, normalize.py
│   ├── align/                 anchors.py, dp.py, moves.py, splitmerge.py, measures.py
│   ├── changes/               features.py, softmax.py, boilerplate.py, numeric.py, rank.py
│   ├── watch/                 poll.py, digest.py
│   ├── index/                 versions.py, bm25.py, dense.py, fuse.py, rerank.py
│   ├── qa/                    analyze.py, route.py, plan.py, generate.py, verify.py, machine.py
│   ├── llm/                   client.py, providers.py, cache.py
│   ├── backtest/              signal.py, prices.py, engine.py, stats.py
│   ├── db/                    models.py, session.py
│   ├── api/                   FastAPI app (slice 2)
│   ├── mcp/                   thin MCP server (slice 2)
│   └── cli.py
├── migrations/                Alembic
├── eval/
│   ├── alignment/             gold/*.jsonl, sample.toml, results/
│   ├── changes/               labels.jsonl, relabel.jsonl, results/
│   ├── qa/                    own_set.jsonl, route_labels.jsonl, judge_labels.jsonl, results/
│   └── README.md              how each number is produced
├── tools/labeler/             local-only labelling UI
├── tests/                     unit/, integration/, fixtures/ (small public filing excerpts)
├── web/                       Next.js app (slice 2)
├── docs/                      RESULTS.md (generated), WRITEUP.md, COMPLIANCE.md
└── data/                      gitignored: raw/, text/, parquet/, cache/, models/
```

### 3.3 Environment variables (`.env`, never committed)

| Variable | Purpose |
|---|---|
| `FL_SEC_USER_AGENT` | `"Name contact@email"` for EDGAR |
| `FL_DATABASE_URL` | Local Docker Postgres. Development and tests use only this. |
| `DATABASE_URL` | Hosted Neon Postgres, pooled. Deployed app only (slice 2). |
| `DATABASE_URL_UNPOOLED` | Hosted Neon Postgres, direct. Alembic migrations against Neon (slice 2). |
| `FL_DATA_DIR` | Defaults to `./data` |
| `FL_LICENSED_DIR` | Defaults to `~/filinglens-licensed`; unused until CRSP |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | LLM providers |
| `FL_HOLDINGS_FILE` | Defaults to `./holdings.local.toml` (gitignored) |

---

## 4. Universes

A universe is a TOML file listing CIKs (or a rule to derive them), form types and a year
range. Every command takes `--universe`.

| Name | Contents | Used for | Size (estimate) |
|---|---|---|---|
| `demo` | XOM, original 10-K, FY2021–2023 | R1 development comparison | 3 filings |
| `t0_dev` | 5 hand-picked companies, 10-K, fiscal 2018–present | Development, unit/integration tests | ~35 filings |
| `t1_rag` | Every company in the FinanceBench open set + the author's holdings; 10-K, fiscal 2014–present | RAG, alerts, alignment eval, deployed app | ~40–60 companies, ~500 filings |
| `t2_lite` | Companies in SEC `company_tickers.json` (currently listed only), 10-K, fiscal 2010–present | Building and testing the signal pipeline and backtest engine | tens of thousands of filings |
| `t2_full` `[EXPANSION]` | All 10-K filers that map to CRSP common stocks, fiscal 2000–present | The reportable backtest | ~100k+ filings |

`t2_lite` is survivorship-biased by construction (delisted firms are missing). It exists
to exercise the pipeline at scale. No return result computed on it is ever reported
(§11.4).

Form types: `10-K` and `10-K405`. Amendments (`10-K/A`) and transition reports
(`10-KT`) are downloaded into the manifest but excluded from alignment pairs and signals.
10-Q support is `[EXPANSION]` (§15).

---

## 5. Ingestion and parsing (slice 1)

### 5.1 EDGAR endpoints

| Need | Endpoint |
|---|---|
| Ticker ↔ CIK | `https://www.sec.gov/files/company_tickers.json` |
| A company's filing list | `https://data.sec.gov/submissions/CIK{cik:010d}.json` (plus the paged files it references for older filings) |
| All filings in a quarter (bulk universes) | `https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/form.idx` |
| A filing's documents | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{primary_document}` |
| XBRL facts | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` |

Record for every filing: `cik`, `accession`, `form`, `period_of_report` (fiscal period
end), `filed_date`, **`accepted_at`** (the acceptance timestamp, needed for
point-in-time work in §11.2), `primary_document`, `sic`.

### 5.2 Fetcher

- One shared async token bucket at 8 requests/second across all workers.
- Retries: exponential backoff with jitter, max 5 attempts, on 429/403/5xx/timeouts.
- Resumable and idempotent: a `filing` manifest row has `fetch_status`
  (`pending|ok|failed|skipped`; `skipped` = amendment or transition report, recorded but
  not downloaded) and `raw_sha256`. Re-running skips `ok` rows.
- Download the **primary document only**, not the full submission with exhibits.
- Storage:
  - `t0`/`t1`: keep raw HTML at `data/raw/{cik}/{accession}/` (zstd) so the parser can be
    re-run and improved without re-fetching.
  - `t2_*`: extract text immediately, store zstd-compressed text plus the raw hash and
    URL, and discard the HTML. Raw HTML for the full universe would run to hundreds of
    gigabytes (estimate); extracted text is roughly an order of magnitude smaller.
- Expose `fl ingest --universe X [--since YEAR] [--limit N]` and print a summary:
  fetched, skipped, failed, bytes.

### 5.3 HTML to blocks

Input: primary document (HTML for modern filings; plain text for many pre-2001 ones).
Output: an ordered list of blocks `{kind: text|table|heading, text, html_offset}`.

1. Drop `<ix:header>`, hidden elements (`display:none`), scripts and styles. Unwrap
   inline XBRL tags, keeping their text.
2. Treat block-level elements (`p`, `div` with only inline children, `li`, `td` outside
   data tables, headings) as block boundaries.
3. A `<table>` is a *data table* if at least 30% of its non-empty cells are numeric;
   otherwise it is layout and is flattened into text blocks. A data table becomes one
   `table` block rendered as pipe-delimited rows, with the nearest preceding text line
   kept as its caption.
4. Remove page furniture: lone page numbers, repeated running headers/footers (a short
   line appearing ≥ 5 times in the document), "Table of Contents" back-links.
5. Normalise Unicode (NFKC), non-breaking spaces, smart quotes, and whitespace.
6. Heading detection: a short block (≤ 120 characters) that is bold/underlined/all-caps
   or matches an Item pattern is a `heading`.

### 5.4 Item segmentation

Pattern (case-insensitive, at the start of a block):

```
^\s*item\s+(1a|1b|1c|1|2|3|4|5|6|7a|7|8|9a|9b|9c|9|10|11|12|13|14|15|16)\b\s*[\.:\-–—]?
```

Each Item heading usually appears twice: in the table of contents and in the body.
Resolution rule: find the sequence of matches that is in canonical Item order and
maximises total text between consecutive headings (dynamic programming over candidate
matches; the table-of-contents copies are adjacent with almost no text between them and
lose).

Era rules (do not treat a missing section as a parse failure):

| Item | Exists for |
|---|---|
| 1A Risk Factors | Fiscal years ending on or after 2005-12-01 |
| 1B Unresolved Staff Comments | Same era as 1A |
| 1C Cybersecurity | Fiscal years ending on or after 2023-12-15 (verified, §16) |
| 9C | Filings made on or after 2021-05-05 (verified, §16). Optional in every era; never required for `parse_status` |

Each filing gets `parse_status`:

- `ok` — Items 1, 7 and 8 found, in order, and (if the era requires it) 1A found with
  ≥ 2,000 characters.
- `partial` — some required Items missing, or an Item is suspiciously short (often
  "incorporated by reference to the proxy statement / annual report"). Record which.
- `failed` — fewer than three Items found, or extracted text under 20,000 characters.

**Never silently fill in a failed parse.** A pair where either side is not `ok` for the
Item in question is excluded from section-level work and counted in coverage reports.
`fl parse --report` prints parse-success rate by fiscal year and by status reason.

### 5.5 Paragraphs

The alignment unit is the paragraph.

- A paragraph is one `text` or `table` block within an Item. Headings are not
  paragraphs; they are carried as `heading_path` (the stack of headings above the
  paragraph within its Item).
- Merge a block shorter than 40 characters into the following block unless it is a
  heading. Bullet items stay separate paragraphs.
- Stored fields: `filing_id`, `item`, `seq` (order within the filing), `heading_path`,
  `text`, `is_table`, `n_tokens`, `exact_hash`, `masked_hash`.

Normalisation (`parse/normalize.py`), used for hashing and similarity, never for display:

- `norm_exact`: lowercase, collapse whitespace, strip punctuation.
- `norm_masked`: `norm_exact` with dates → `<date>`, 4-digit years → `<year>`, all other
  numbers (including `$1.2 billion`, `12%`, `(3,400)`) → `<num>`.
- `exact_hash = sha1(norm_exact)`, `masked_hash = sha1(norm_masked)`.

Masking is for *matching only*. The numeric values are kept separately for the
numeric-delta check (§7.4), because a number changing can be the most material edit.

---

## 6. Alignment engine (slice 1) — the core

### 6.1 Problem

Given the paragraph lists of one Item in two consecutive annual reports of the same
company — `A` (older) and `B` (newer) — produce a set of edges. Every paragraph of `A`
and of `B` appears in exactly one edge.

| Label | Meaning | Old side | New side |
|---|---|---|---|
| `unchanged` | `exact_hash` equal | 1 | 1 |
| `rollforward` | `masked_hash` equal, `exact_hash` differs (only numbers/dates changed) | 1 | 1 |
| `modified` | Same paragraph, reworded; similarity in [τ, 1) | 1 | 1 |
| `moved` | Matched, but out of order relative to its neighbours | 1 | 1 |
| `split` | One old paragraph became two adjacent new ones | 1 | 2 |
| `merged` | Two adjacent old paragraphs became one new one | 2 | 1 |
| `added` | No counterpart in `A` | 0 | 1 |
| `deleted` | No counterpart in `B` | 1 | 0 |

A pair is eligible when both filings are the same CIK, both are non-amended 10-Ks, and
their `period_of_report` dates are 9–15 months apart.

### 6.2 Similarity function

`sim(a, b)` = cosine similarity of TF-IDF vectors over `norm_masked` text, word
unigrams + bigrams, sublinear TF. IDF is fitted **once** on the paragraphs of the
`t1_rag` universe and saved to `data/models/idf_v1.npz`, so scores are comparable across
pairs and reproducible. Version the IDF file; changing it invalidates stored alignments.

### 6.3 Algorithm

**Stage 1 — anchors (patience-diff style).** Find paragraphs whose `masked_hash` occurs
exactly once in `A` and exactly once in `B`. Take the longest increasing subsequence of
these matches by position; those are *anchors* (labelled `unchanged` or `rollforward`).
Unique matches outside the LIS are *move candidates*.

**Stage 2 — gap alignment (Needleman–Wunsch).** Between each pair of consecutive
anchors lies a gap `(A[i1:i2], B[j1:j2])`. Align it with global dynamic programming:

```
score(i, j) = max(
    score(i-1, j-1) + (sim(a_i, b_j) - τ),   # match, only worth it if sim > τ
    score(i-1, j),                            # a_i deleted (gap cost 0)
    score(i, j-1),                            # b_j added   (gap cost 0)
)
```

Default `τ = 0.50`, tuned on the dev pairs (§6.5). Subtracting τ means a weak match
is never preferred over leaving both sides unmatched. If a gap exceeds 400 × 400 cells,
fall back to a banded DP (band = 50 around the diagonal) and log it.

**Stage 3 — moves.** Take all still-unmatched old paragraphs and unmatched new
paragraphs in the Item (plus Stage-1 move candidates). Greedily pair by descending
`sim`, one-to-one, while `sim ≥ 0.80`. Label `moved`. Then repeat across Items in the
same filing (text relocated from Item 7 to Item 1A, for example), recording both Items.

**Stage 4 — split and merge.** For each remaining `added` paragraph `b` adjacent to a
matched pair `(a, b')`: if `sim(a, b' ⧺ b) − sim(a, b') ≥ 0.10` and token containment
of `b` in `a` ≥ 0.80, relabel as `split`. Symmetric rule for `merged`. Only 1→2 and
2→1 are handled; anything larger stays as modified + added/deleted `[EXPANSION]`.

**Output.** `alignment_edge` rows (§12) with the label, `sim`, and for non-identical
matches a word-level diff summary (`n_ins`, `n_del`, changed-token ratio) computed with
a standard sequence diff over tokens.

Determinism: ties are broken by lower index. Same inputs and IDF version must give
byte-identical output; there is a test for this.

### 6.4 Document-level measures

Computed for every eligible pair, for whole documents and per Item:

- `sim_cosine` — cosine of term-frequency vectors of the two texts.
- `sim_jaccard` — Jaccard similarity of their term sets.
- `change_intensity` — our own measure from the alignment: share of the new filing's
  tokens that sit in `added`, `modified`, `split` or `merged` paragraphs, after
  removing changes classified cosmetic (§7).

The paper uses four similarity measures (cosine, Jaccard, minimum edit distance and a
"simple" side-by-side measure). This was confirmed from a secondary source only on
2026-11-15; `[VERIFY against the paper]` remains open for task 3.1. Slice 1 depends only
on cosine and Jaccard being among them. Cosine and Jaccard are the
replication measures; `change_intensity` is the contribution. Minimum-edit and simple
are `[EXPANSION]`.

For the **replication**, use whole-document similarity as the paper does. Section-level
measures are used only where the section exists and parsed `ok` in both years.

### 6.5 Alignment evaluation

This produces the first resume number.

**Gold data.** 30 filing pairs from `t1_rag`, Items 1A and 7 only (aligning whole
10-Ks by hand is weeks of work).

- Stratify across sector (SIC division), era (2006–2012, 2013–2019, 2020–present) and
  length tercile. Record the sampling in `eval/alignment/sample.toml` with a seed.
- Deliberately include at least 6 pairs with visible restructuring (sections merged,
  split or reordered).
- Split: 10 dev pairs (used to tune τ and thresholds), 20 test pairs. **The test pairs
  are scored once, at the end.** Record the commit hash of that run.

**Labelling tool** (`tools/labeler`, local only). It pre-fills *exact-hash matches
only* and the author adjudicates everything else by hand. It must never pre-fill from
the aligner's own output, or the gold data inherits the aligner's mistakes. Gold format:
one JSON line per edge, same schema as `alignment_edge`.

**Metrics.**

- Edge precision, recall and F1, where an edge is correct if its old-side and new-side
  paragraph ids match a gold edge. Report twice: over all edges, and over
  **non-identical edges only** (identical ones are trivially right and inflate scores).
  The non-identical number is the headline.
- Label accuracy on correctly matched edges.
- 95% confidence intervals by bootstrap **over pairs** (10,000 resamples), because
  pairs are the independent units.

**Baselines** (same gold data), to show the algorithm earns its complexity:

1. `difflib.SequenceMatcher` over paragraph `masked_hash` sequences.
2. Greedy best-match by `sim` with threshold τ, no ordering constraint.
3. Full algorithm with each of Stages 3 and 4 switched off (ablation).

Results go to `eval/alignment/results/{run_id}.json` and a table in `docs/RESULTS.md`.

### 6.6 Tests

- Unit: identical lists; pure insertion; pure deletion; one modified paragraph; a
  move; a split; a merge; duplicated boilerplate paragraph (non-unique hash must not
  become an anchor); empty side.
- Property (`hypothesis`): every paragraph appears in exactly one edge; aligning `A`
  with itself yields all `unchanged`; anchors are order-preserving; output is
  deterministic.
- Integration: two real filing pairs in `tests/fixtures/` (public data) with snapshot
  outputs.

---

## 7. Change classification and alerts (slice 1)

### 7.1 Taxonomy

Annotation uses six labels. The model is trained on three, until label counts justify
more.

| Annotation label | Training class |
|---|---|
| `formatting_reorder` | cosmetic |
| `boilerplate_refresh` | cosmetic |
| `numeric_rollforward` | rollforward |
| `new_topic` | substantive |
| `removed_topic` | substantive |
| `substantive_reword` | substantive |

Definition of *substantive*: the change alters the information a reader has about the
company. Write 2–3 examples per label into `eval/changes/GUIDE.md` before labelling and
do not change definitions mid-way without relabelling.

Rules decide first: `unchanged` edges are ignored; `rollforward` edges are class
`rollforward` without the model. The model classifies `modified`, `moved`, `split`,
`merged`, `added` and `deleted` edges as cosmetic vs substantive.

### 7.2 Boilerplate score

Many edits are language every company adopted that year (new accounting standard
wording, pandemic language, new disclosure rules). For each paragraph, compute the
fraction of its 5-word shingles (over `norm_masked`) that appear in filings of at least
`k = 10` **other** companies in the same fiscal year. Implementation: hash shingles to
64-bit ints, store `(shingle_hash, cik, fiscal_year)` in Parquet, compute document
frequency with DuckDB. `boilerplate ∈ [0, 1]`; `novelty = 1 − boilerplate`.

On `t1_rag` alone the cross-company pool is small; once `t2_lite` text exists, compute
shingle frequencies from it.

### 7.3 Model

Softmax regression written in NumPy (the author's own implementation, extended from the
earlier classifier project): L2 regularisation, full-batch gradient descent or L-BFGS,
class weights for imbalance. Sanity-check against scikit-learn `LogisticRegression` on
the same features; the two should agree closely.

Features per edge:

- Frozen sentence embedding of the old text, the new text, and their difference
  (zero vector for a missing side). Same local embedding model as §8.2.
- `sim`, changed-token ratio, length ratio, edge label one-hot.
- `boilerplate` of the new side (old side for `deleted`).
- Item one-hot (1A, 7, other), `is_table`.
- Numeric-delta features from §7.4.

Labelling protocol:

- Seed: 100 edges sampled across companies and labels. Then active learning: batches
  of 25 chosen by highest predictive entropy, to about 300.
- **Hold out by company** (`GroupKFold` on CIK). Never split by paragraph.
- Single-annotator consistency: at least 7 days later, relabel 50 edges blind and
  report Cohen's κ in the write-up.
- Report macro-F1 and per-class precision/recall with company-grouped cross-validation.

### 7.4 Numeric-delta check

For `rollforward` and `modified` edges, extract numbers from old and new text with
their unit context (`%`, `$`, million/billion, plain) and pair them positionally within
the aligned paragraph.

Raise a numeric alert when all hold:

- the number is not a date, year, page or note reference;
- it is not in a `table` block (tables roll forward every year by design);
- relative change ≥ 25% (config), or a percentage changes by ≥ 5 points (config).

Example this must catch: "one customer accounted for 10% of revenue" → "35% of revenue".

### 7.5 Ranking and presentation

`alert_score = P(substantive) × novelty × item_weight` (weights: 1A = 1.0, 7 = 0.9,
other = 0.6; config). Per filing, show the top 10 text alerts and all numeric alerts.

Each alert shows: Item and heading path, old text and new text with a word-level diff,
the class and score, and a link to the filing on EDGAR.

An LLM writes a one- or two-sentence summary of each shown alert from the old and new
text. This is the only LLM use in slice 1. If no provider is available, the alert is
shown without a summary; nothing else depends on the LLM.

### 7.6 Watcher

- Holdings live in `holdings.local.toml` (gitignored): a list of tickers. No
  quantities. Tickers resolve to CIKs via `company_tickers.json`.
- `fl watch` polls the submissions endpoint for each holding, finds 10-K accessions not
  yet in the manifest, and runs ingest → parse → align → classify → digest.
- Output: a digest at `data/digests/{date}.md` and rows in the `alert` table.
- Summaries for holdings use only providers tagged `private_ok` (§10.2), since the
  request itself reveals what the author holds.
- Scheduling in slice 1 is a local scheduled job. A hosted schedule (GitHub Actions
  with holdings stored as an encrypted secret, digests written to the database, nothing
  in logs) is slice 2.
- `fl backfill --ticker X --years N` runs the same pipeline over past filings, which is
  how the feature is demonstrated outside filing season.

### 7.7 Alert evaluation

Use the full-digest R4 protocol in §14 for release decisions. Independently mark must-see changes before viewing output, judge every displayed text and numeric alert, and report misses and reading time. For a supplementary text-ranking diagnostic, sample 100 shown alerts from **held-out companies** (not the author's holdings: eight
companies is too few and not representative). Judge each useful / not useful against
the written guide. Report precision of shown alerts and precision@5 per filing, with a
bootstrap interval over filings. Compare against a baseline that ranks by `1 − sim`
alone.

---

## 8. Temporal RAG (slice 2)

### 8.1 Versioned index

Built from alignment edges across all consecutive pairs of a company.

- A **chain** is one logical paragraph through time. A **version** is one distinct text
  of that chain with `valid_from_fy` and `valid_to_fy`.
- `unchanged` edge → extend the current version's `valid_to_fy`. No new row.
- `rollforward`, `modified`, `moved`, `split`, `merged` → new version in the same
  chain, `predecessor_id` set. (For `split`, both new paragraphs join the chain; for
  `merged`, the new version continues the first chain and closes the second with a
  pointer.)
- `added` → new chain. `deleted` → close the chain.
- If a pair is not eligible or not parsed `ok`, chains break there and restart; the
  break is recorded so retrieval does not imply continuity.

Only versions are embedded and indexed. Report the **deduplication ratio**
(paragraph instances ÷ versions) — a measured number for the resume.

Retrieval is time-aware:

- Point-in-time ("in fiscal 2022"): filter `valid_from_fy ≤ 2022 ≤ valid_to_fy`.
- Change ("how has X changed from 2021 to 2024"): find relevant chains, return each
  chain's versions over the range in order, with diffs. No reliance on similarity
  search happening to surface the right years.

### 8.2 Retrieval stack

| Stage | Detail |
|---|---|
| Sparse | Own BM25 (`k1 = 1.2`, `b = 0.75`) over version text; inverted index in SciPy sparse, persisted, loaded in memory. Top 50. |
| Dense | Local open embedding model, 384 dimensions (`BAAI/bge-small-en-v1.5`, run through ONNX with `fastembed`; confirmed 2026-11-15, §16); pgvector HNSW, cosine. Top 50. |
| Filter | Applied to both: `cik`, fiscal-year validity, optionally `item`. |
| Fusion | Reciprocal rank fusion, `score = Σ 1 / (60 + rank)`. Top 20. |
| Rerank | Small cross-encoder, ONNX int8, CPU. Top 8 to the generator. |

Table blocks are indexed by caption + header row + row labels; the full table is passed
to the generator as Markdown.

### 8.3 Query state machine

Hand-written, in `qa/machine.py`. Every transition writes a trace row (step, latency,
provider, tokens, cache hit).

```
ANALYZE → ROUTE → PLAN → RETRIEVE → GENERATE → VERIFY ─┬─▶ DONE
                              ▲                        ├─▶ RETRY (once) ─▶ RETRIEVE
                              └────────────────────────┘
                                                       └─▶ ABSTAIN
```

- **ANALYZE** (deterministic first): resolve company names/tickers to CIKs; extract
  fiscal periods by rule ("FY2022", "last three years", "Q2 2023"). Ambiguity that
  rules cannot settle goes to one small LLM call with a JSON schema.
- **ROUTE**: one of `xbrl_fact`, `table`, `text`, `change`. Implementation v1: rules
  plus one schema-constrained LLM call, with a rule-only fallback if the call fails.
  `[EXPANSION]`: replace with the softmax classifier trained on the route labels.
- **PLAN**: if the question spans several periods or companies, emit one sub-query per
  (company, period), max 6, run with `asyncio.gather`. Otherwise a single sub-query.
- **GENERATE**: the model returns JSON: `claims[]`, each with `text`, `citations[]`
  (version ids or fact ids from the supplied context) and optional `value` + `unit`.
  Output is treated as untrusted: schema-validated, and citations not in the supplied
  context are rejected.
- **VERIFY**: §8.6.

### 8.4 Routes

- `text` → §8.2 over narrative versions.
- `table` → §8.2 restricted to table blocks.
- `change` → chain walk (§8.1).
- `xbrl_fact` → §8.5; on no match falls back to `table`.

### 8.5 XBRL facts

Load `companyfacts` JSON into a `fact` table: `cik, taxonomy, tag, unit, period_start,
period_end, fy, fp, form, accession, filed, value`.

- `config/concepts.toml` maps about 40 common metrics to ordered lists of candidate
  `us-gaap` tags (revenue alone has several historical tags). No match → fall back to
  the table route. Company-specific extension tags are not resolved in v1.
- Restatements: the same period can have several values from different filings. For
  Q&A return the **latest filed** value, cite its filing, and flag when it differs from
  the first-reported value. (For any backtest use of fundamentals, use first-reported
  only. The v1 backtest uses none.)
- Derived metrics (margins, growth, ratios) are computed in Python from a small formula
  registry. The model picks a formula and its inputs through structured output; it does
  not do arithmetic.

### 8.6 Verification

Three checks, cheapest first:

1. **Structural** — every claim has at least one citation, and each cited id was in the
   supplied context.
2. **Numeric** (deterministic) — every number in a claim either appears in a cited
   passage or fact (allowing scale and rounding: thousands/millions/billions, 1%
   tolerance) or is the output of a registered formula over cited facts.
3. **Entailment** — a small local NLI cross-encoder scores (cited passage → claim).
   Threshold tuned on a labelled dev set. Fallback when the model cannot be loaded
   (memory-constrained host): a judge call to a *different* provider than the generator.

A failed claim triggers **one** retry: re-retrieve using the failed claim as an extra
query, regenerate with the failure reason. Still failing → the claim is dropped and the
answer is marked partially supported; if no claim survives, ABSTAIN with the reason.

Do not use the generating model's self-reported confidence as a gate; it is poorly
calibrated.

### 8.7 API, UI, MCP

- FastAPI: `POST /ask`, `GET /filings/{cik}`, `GET /changes/{cik}/{fy}`,
  `GET /alerts`, `GET /trace/{id}`. Per-IP and global daily caps; cached example answers.
- Next.js UI: ask page with clickable citations opening the paragraph; a changes page
  with side-by-side diff; a chain view showing one paragraph across years.
- MCP server (thin, about a day): `search_filings`, `get_section`, `get_fact`,
  `compare_sections`, `get_changes`. It wraps existing functions and is not a headline.

---

## 9. Question-answering evaluation (slice 2)

### 9.1 Datasets

1. **FinanceBench open set** (150 questions). Each question references a specific
   document (company, period, type). Map each to an EDGAR accession. The benchmark was
   built from PDFs and includes document types beyond 10-K (10-Q, 8-K, earnings
   releases `[VERIFY]`).
   - Report accuracy on the **covered subset** (documents in our corpus) **and** on all
     150 with uncovered questions counted as wrong. Both numbers, always together.
2. **Own set** (60 questions over `t1_rag`, written by the author with gold answers and
   gold evidence paragraph ids): 20 temporal/change, 20 numeric, 20 narrative. This is
   where the versioned index is expected to show its value.
3. **Route labels**: the gold route for every question in both sets.

### 9.2 Scoring

- Numeric gold answers: deterministic comparison, 1% tolerance after unit normalisation.
- Other answers: an LLM judge from a different provider than the answerer, with a fixed
  rubric returning `correct | incorrect | refused`.
- **Judge calibration**: the author hand-labels 60 answers; report agreement with the
  judge (Cohen's κ). The judge's number is only quoted alongside this.
- Retrieval: recall@k against gold evidence where gold evidence exists.
- Grounded-claim rate: share of claims passing §8.6. Abstention rate.
- Cost per question and p50/p95 latency from traces.

### 9.3 Baseline numbers for context

The FinanceBench paper reports a naive shared-vector-store setup scoring roughly 19%
and much higher scores with oracle context `[VERIFY against the paper before quoting]`.
Quote published baselines only with a citation, and never as if they were run here.

### 9.4 Ablation ladder

Same generator model, same prompts where applicable, cached calls, fixed seed.

| Config | Adds |
|---|---|
| A0 | Naive: fixed 512-token chunks, dense top-5, single generation call |
| A0-time | A0 with fiscal-period filtering on ordinary passages |
| A1 | Same period filter and retrieval budget over paragraph versions; compare directly with A0-time |
| A2 | Hybrid BM25 + dense with RRF |
| A3 | Cross-encoder rerank |
| A4 | Router with XBRL and table routes |
| A5 | Decomposition for multi-period / multi-company questions |
| A6 | Verification with one retry |

For each: accuracy (both datasets, by question type), recall@k, grounded-claim rate,
cost, latency. `fl eval qa --config A3` writes `eval/qa/results/{run_id}.json`;
`fl eval report` regenerates `docs/RESULTS.md`.

Rule: a rung that does not help is cut from the default pipeline, and the write-up says
so with the numbers.

### 9.5 CI

- Smoke eval (20 questions) runs in CI from cached LLM responses; no network calls.
- A drop of more than 3 points on the dev subset against the committed baseline fails
  the check. Refreshing the baseline is an explicit, reviewed change.
- Day-to-day runs use the free model. "Official" numbers come from a small number of
  runs that are recorded with model id, date and commit.

---

## 10. LLM layer

### 10.1 Interface

```python
class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        schema: dict | None = None,     # JSON schema for structured output
        privacy: Literal["public", "private"] = "public",
        purpose: str,                   # "summary" | "route" | "generate" | "judge" ...
    ) -> LLMResult: ...                 # text/json, provider, model, tokens, latency, cached
```

### 10.2 Providers and privacy

`config/models.toml` lists providers in preference order per purpose, each with
`base_url`, `model`, `private_ok` (true only for providers whose terms say API data is
not used for training, and for local models) and rate limits.

- Do **not** hard-code model ids in source. Free-tier model names and limits change;
  check the providers' current documentation when filling in this file. The entries
  needed for slice-1 summaries were verified on 2026-11-15 (§16); re-check at task 2.2.
- Defaults: Gemini free tier for public generation; Groq for private requests and as
  the judge (must differ from the generator); Ollama optional for offline development.
- Most providers accept the OpenAI-compatible request format, so a provider is a base
  URL, a key and a model name.
- Failover: on 429/5xx/timeout move to the next provider allowed for that privacy
  level. A `private` request never falls through to a provider without `private_ok`;
  it fails instead.

This layer is deliberately small (target under ~200 lines). It is plumbing, not a
resume bullet.

### 10.3 Cache

Key = sha256 of (provider-independent canonical request: messages, schema, model id,
temperature). Stored under `data/cache/llm/`. Temperature 0 everywhere. Tests and CI
run with `FL_LLM_MODE=replay`, which errors on a cache miss instead of calling out.

---

## 11. Lazy Prices research track (slice 3)

Reference: Cohen, Malloy and Nguyen, "Lazy Prices", *Journal of Finance*, 2020. Claim:
firms whose periodic reports change more from the prior year tend to earn lower
subsequent returns. **Read the paper's data and methodology sections before coding
this slice** and reconcile every `[VERIFY]` below.

### 11.1 Signal

`data/parquet/signal.parquet`, one row per eligible pair:

`cik, accession, prev_accession, fiscal_year, period_of_report, accepted_at,
sim_cosine, sim_jaccard, change_intensity, n_tokens, n_tokens_prev, parse_status,
parse_status_prev, idf_version, code_version`

Built by `fl signal build --universe X`. No LLM anywhere in this track.

Descriptive results that need no price data (reportable under the fallback): similarity
distribution by year and by sector, year-to-year persistence of a firm's similarity,
coverage and parse-success by year, and the relationship between whole-document
similarity and `change_intensity`.

### 11.2 Point-in-time rules

- A signal becomes known at `accepted_at`. A filing accepted after 16:00 Eastern, or on
  a non-trading day, is known from the next trading day.
- Monthly rebalancing: portfolios formed at the end of month *t* use only signals known
  by the last trading day of *t* and earn returns from month *t + 1*.
- The engine **asserts** for every position that `signal_known_at < return_period_start`.
  This is a hard failure, not a warning.

### 11.3 Price-data interface

```python
@dataclass(frozen=True)
class SourceMeta:
    name: str
    survivorship_free: bool
    reportable: bool          # may results be published as findings?
    license_note: str

class PriceSource(Protocol):
    meta: SourceMeta

    def link(self, cik: str, as_of: date) -> list[str]:
        """Security ids for a company on a date (a CIK can map to several, or none)."""

    def universe(self, month_end: date) -> pd.DataFrame:
        """Eligible securities: security_id, mktcap, price, exchange, is_common."""

    def monthly_returns(self, security_ids: Sequence[str], start: date, end: date) -> pd.DataFrame:
        """security_id, month_end, ret (total return, delisting included), mktcap_lag."""
```

Implementations:

| Class | Data | `survivorship_free` | `reportable` | Built in |
|---|---|---|---|---|
| `SyntheticPriceSource` | Generated, with an optional planted return spread | n/a | false | Slice 3 (first) |
| `FreePriceSource` | A free daily/monthly price source `[OPEN]`, currently listed tickers only | false | false | Slice 3 |
| `CrspPriceSource` | CRSP via WRDS | true | true | `[EXPANSION]` §11.6 |

Factor data for risk adjustment comes from the Kenneth French Data Library, which is
free and public; cite it.

### 11.4 The fallback we go with now

Until CRSP access is confirmed **and** data is pulled, the project claims exactly this:

> Built and validated the filing-change measurement and a point-in-time backtest
> framework; the return effect is not tested because survivorship-bias-free price data
> was not available.

Enforcement in code, not just in prose:

- The engine stamps every output with `source.meta`. If `reportable` is false, result
  files are written under `results/not_reportable/`, charts carry a visible
  "NOT REPORTABLE — survivorship-biased data" watermark, and `fl eval report` refuses to
  copy them into `docs/RESULTS.md`.
- Free-data return numbers never appear in the README, write-up or resume. Free data
  exists to prove the engine runs end to end at scale.

Why not report free-data returns with a caveat: the claimed effect is underperformance
of heavy changers, and firms that later fail or delist are exactly the ones a
currently-listed universe removes. The bias points at the result itself.

### 11.5 Backtest engine

A pure function: `run(signals, source, config) -> BacktestResult`. No I/O inside.

- **Sorting**: each month, rank eligible firms on the similarity measure among firms
  with a signal that became known within the formation window; form quintiles; Q5 =
  most similar (non-changers), Q1 = least similar (changers); long Q5, short Q1.
  Formation window and holding period per the paper `[VERIFY: recollection is a
  three-month holding period with monthly overlapping portfolios]`. Both are config.
- **Weighting**: equal and value (lagged market cap). Both reported.
- **Filters** (config; defaults per the paper `[VERIFY]`): common stocks on major
  exchanges, minimum price, exclusion of the smallest firms.
- **Outputs**: monthly return series per quintile and the long-short spread; mean,
  volatility, Sharpe; t-statistic with Newey–West standard errors; alphas against
  market, three-factor and five-factor + momentum models; turnover; returns net of
  transaction costs at configurable basis points per unit turnover.
- **Sub-periods**: the paper's original sample window, the years after its sample
  ends, and the years after publication. Break dates are config `[VERIFY sample dates]`.
- **Robustness**: each similarity measure separately; `change_intensity` versus
  whole-document cosine; 10-K only (a documented deviation: the paper also uses 10-Qs).

Tests (all with `SyntheticPriceSource`):

1. Planted spread of known size is recovered within tolerance.
2. Placebo: shuffled signals give a spread statistically indistinguishable from zero.
3. Look-ahead: shifting every signal one month later changes only positions from that
   month onward; a deliberately leaked signal trips the §11.2 assertion.
4. Delisting: a security with a terminal −100% return is included, not dropped.
5. Determinism and weight sums (each leg's weights sum to 1).

### 11.6 CRSP expansion `[EXPANSION]`

Everything above is built so that this is one new class plus one run.

**Gate — do not start until all are true:**

- [ ] WRDS account approved and it includes CRSP for undergraduates.
- [ ] Library confirms in writing: (a) a public portfolio write-up with aggregate
      results counts as permitted academic use; (b) the blackout dates for
      undergraduate accounts; (c) the required citation wording; (d) whether a monthly
      long-short portfolio return series counts as an aggregate result or as "data".
- [ ] WRDS AI policy read; §2.3 rule 4 still matches it.

**Pull** (run by the author in a terminal, not by an AI session):
`scripts/pull_crsp.py` uses the `wrds` package and writes Parquet to `FL_LICENSED_DIR`.

| Need | Source `[VERIFY all table and column names in current WRDS documentation]` |
|---|---|
| Monthly returns, price, shares outstanding | CRSP monthly stock file. CRSP has moved to a newer file format; the legacy tables were `crsp.msf` (+ `crsp.msenames`, `crsp.msedelist`), and the newer format folds delisting returns into the return series. Use whichever the subscription serves and handle delisting accordingly. |
| Security type and exchange | Names/history table for the same format (share codes for common stock, exchange codes for NYSE/AMEX/NASDAQ) |
| CIK ↔ PERMNO | CRSP/Compustat Merged link table plus Compustat company CIK, or the WRDS SEC linking table if subscribed. Links are date-ranged; respect `link start/end`. |

Date range: January 1995 to the latest available month. Monthly data for the whole
market is small (well under a gigabyte, estimate), so pull everything once before the
blackout.

**Implement** `CrspPriceSource` against the documented schema and
`tests/fixtures/crsp_synthetic/` — a fabricated dataset with the same columns. The
implementer never sees real rows. Unit tests run on the synthetic fixture in CI; the
author runs `fl backtest run --source crsp` locally.

**Guards:**

- `FL_LICENSED_DIR` must resolve outside the repo; the loader refuses otherwise.
- Pre-commit hook and a CI check fail on any `*.parquet`, `*.csv`, `*.sas7bdat` or
  `*.dta` file in the repo, and on the strings `permno`/`PERMNO` in any data file.
- Result writer for `reportable` sources emits only: portfolio-level statistics, the
  charts, and (if the library allows) portfolio return series. Never security-level
  rows, never the link table.
- `docs/COMPLIANCE.md` records what was pulled, when, under which terms, and what was
  published.

If access never arrives, nothing is wasted: slice 3 ships with §11.4's claim.

---

## 12. Data model (app database)

Types abbreviated. All tables have `id` and `created_at`.

```
company(cik PK, name, ticker, sic, sector)

filing(id, cik FK, accession UNIQUE, form, period_of_report, fiscal_year, filed_date,
       accepted_at, primary_document, raw_sha256, fetch_status, parse_status,
       parse_notes JSONB, parser_version)

paragraph(id, filing_id FK, item, seq, heading_path TEXT[], text, is_table,
          n_tokens, exact_hash, masked_hash)
          INDEX (filing_id, item, seq), INDEX (masked_hash)

alignment_pair(id, cik, old_filing_id FK, new_filing_id FK, item NULLABLE,
               eligible, exclusion_reason, idf_version, aligner_version,
               sim_cosine, sim_jaccard, change_intensity_raw, change_intensity)

alignment_edge(id, pair_id FK, label, old_paragraph_ids INT[], new_paragraph_ids INT[],
               sim, n_ins, n_del, changed_ratio, cross_item BOOL)

change_label(id, edge_id FK, annotation_label, labelled_at, pass)   -- pass 1 / relabel 2
change_pred(id, edge_id FK, model_version, p_cosmetic, p_rollforward, p_substantive,
            boilerplate, alert_score)
numeric_alert(id, edge_id FK, old_value, new_value, unit, rel_change)
alert(id, filing_id FK, edge_id FK, kind, rank, summary, summary_model)

chain(id, cik, item, opened_fy, closed_fy NULLABLE, continued_as_chain_id NULLABLE)
version(id, chain_id FK, predecessor_id NULLABLE, text, is_table, heading_path,
        valid_from_fy, valid_to_fy, first_filing_id FK, embedding VECTOR(384))
        INDEX hnsw (embedding vector_cosine_ops), INDEX (chain_id, valid_from_fy)

fact(id, cik, taxonomy, tag, unit, period_start, period_end, fy, fp, form,
     accession, filed, value)
     INDEX (cik, tag, period_end)

trace(id, request_id, step, provider, model, tokens_in, tokens_out, latency_ms,
      cached, detail JSONB)
```

Bulk-tier Parquet datasets: `text/` (one file per filing), `shingles/`, `signal`,
`backtest results`. Schemas are defined as dataclasses next to the code that writes them.

Every derived row carries the version of the code or model that produced it
(`parser_version`, `aligner_version`, `idf_version`, `model_version`), so results are
reproducible and stale rows can be found.

---

## 13. Testing, CI, deployment

**Tests.** Unit tests per module; integration tests over `t0_dev` fixtures committed to
the repo (public filings, trimmed); no test touches the network (`respx` mocks for
EDGAR; `FL_LLM_MODE=replay` for LLMs). Target: the aligner and the backtest engine have
the densest coverage, because their correctness is the project's claim.

**CI (GitHub Actions).** On every PR: `ruff`, `mypy` (strict on `align/`, `backtest/`),
`pytest`, the licensed-data guard, and from slice 2 the smoke eval.

**Workflow.** Feature branches and PRs into `main`, even solo; small commits at
working milestones. Commits carry no AI attribution lines.

**Deployment (slice 2).**

| Piece | Host | Notes |
|---|---|---|
| Database | A free hosted Postgres with pgvector (default: Neon) `[OPEN]` | Check current free-tier storage against the measured size of `t1_rag` before committing |
| API | A free container host `[OPEN]` | Memory budget is the constraint: embedding model + reranker + BM25 index must fit. If they do not, drop the reranker in production and say so. |
| Frontend | Vercel | |
| Scheduled watcher | GitHub Actions cron | Holdings as an encrypted secret; nothing identifying in logs |

Everything heavy (ingest, parse, align, embed, classify, signal, backtest) runs offline
on the laptop and uploads results. The hosted app only reads.

---

## 14. Build plan

The completed foundation comprises tasks 0.1–0.4, the EDGAR client (1.1), and the ingestion implementation (1.2). The original task numbers identify component briefs. The delivery sequence and acceptance criteria below govern their use.

| Milestone | Work and acceptance | Decision at review |
|---|---|---|
| R1 · Baseline comparison | One development company, three consecutive annual filings, two verified Item 1A redlines, source links and documented baseline errors | Inspect the HTML and source passages. Select fixes and reader tasks. |
| R2 · Reader sessions | Independent must-see references, observed usual-workflow and baseline sessions, per-reader time and misses | Choose the first problem worth solving. |
| R3 · Matching | Expand parser coverage and build only the matching features selected after R2. Compare with simple methods on development pairs | Review before freezing for the one held-out test run (§6.5). |
| R4 · Portfolio release | Evaluate the full source-linked digest for Items 1A and 7, including numeric alerts, against blinded references and reading time | Release, narrow the claim, or keep the simpler baseline. |
| R5 · History experiment | Evaluate a paragraph-history view and a fiscal-year-filtered search control on multi-year questions | Decide whether cited Q&A and further retrieval work are justified. |

The [implementation and review brief](docs/briefs/reader-first.md) defines inputs, commands, deliverables, human work, and review packets. Summaries, hosted chat and MCP require a reader need and a later scope decision. The return study in §11 is unscheduled, including its synthetic fallback.

---

## 15. Room for expansion

Designed for, not built now. Each names the seam where it attaches.

| Expansion | Seam |
|---|---|
| CRSP backtest | `PriceSource` (§11.3, §11.6) |
| 10-Q filings (compare with the same quarter a year earlier) | Item patterns in `parse/items.py`; pair eligibility in `align`; needed for full fidelity to the paper |
| `t2_full` universe back to 2000 and plain-text-era filings | `config/universes`; a text-format parser path in `parse/html.py` |
| Remaining paper measures (minimum edit, simple) | `align/measures.py` |
| Size / book-to-market controls | Needs fundamentals as first reported; `fact` table already keeps filing provenance |
| Learned router | Softmax on route labels replaces the LLM call in `qa/route.py` |
| Many-to-many split/merge | `align/splitmerge.py` |
| Company-specific XBRL extension tags | `config/concepts.toml` + a per-company resolver |
| 8-K and earnings releases (raises FinanceBench coverage) | New form parser; no alignment needed |
| Multi-user accounts and email digests | `watch/` + auth in `api/` |
| 40-F (Canadian cross-listed filers) | New form parser; different structure, no Items |

---

## 16. Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-18 | Keep the strict `compare_key` (all punctuation retained) and freeze the comparison at tag `r2-freeze` (merge of PR #15, reviewed head a534e83) for the R2 sessions. Four XOM paragraphs now show punctuation-only changes. Candidate later design, built only if R2 shows the cost: punctuation-only edits separate groups and sit under a collapsed "punctuation changed" label with both wordings kept | An allowlist of meaningful punctuation silently misses cases such as `.5%` → `5%`, `A+` → `A`, `6:1` → `61`. Distraction is an R2 outcome to measure, not to pre-empt |
| 2026-11-17 | R1 baseline accepted for development. Before R2, preserve numeric signs and units in comparison keys, enforce §6.1 eligibility, and show ambiguous replacement groups as neutral earlier/later text with explicit count labels. Keep matching frozen during reader sessions. | The reproduced XOM comparison hides a new regulatory bullet inside a replacement despite zero standalone additions. The equality key also folds a sign reversal. See TODO.md for acceptance cases. |
| 2026-11-17 | Table rows keep dash-only cells as `—` in their column; truly empty cells and lone `$ % )` still drop or glue. Data-table detection is unchanged | Dropping the dashes shifted values into the wrong columns (Apple FY2023 fair-value table) |
| 2026-11-17 | R1 builds tasks 1.3–1.5 in full rather than a reduced Item 1A extractor | The parser is needed again at R3, and choosing the body heading over the table of contents (1.4) is what a shortcut gets wrong |
| 2026-11-17 | Adopt R1–R5 (§14). Start with XOM FY2021–23, source-linked baseline and reader review. Defer classifier, LLM summaries, hosted chat, MCP and the return study pending separate decisions. | Measure misses and reading time early enough to change the design. Earlier component briefs describe options for later reviews. |
| 2026-11-13 | Pivot from an eight-component plan to one alignment engine powering alerts, RAG and research | Depth over breadth; filing Q&A alone is commodity |
| 2026-11-13 | No agent framework, no LLM-built knowledge graph, no fine-tuning | Cost, defensibility in interviews, scope |
| 2026-11-13 | Hand-align Items 1A and 7 only; pre-fill exact matches only | Labelling cost; avoid biasing gold data toward the aligner |
| 2026-11-13 | Annotate six change labels, train three | About 300 labels cannot support six classes |
| 2026-11-13 | Mask numbers for matching, check numeric deltas separately | Masking alone would hide material numeric changes |
| 2026-11-13 | Free-data backtest results are never reported | Survivorship bias points at the effect being tested |
| 2026-11-13 | Build without CRSP; integrate later behind `PriceSource` | Access unconfirmed; licensed data may not be shown to a model anyway |
| 2026-11-13 | v1 backtest is 10-K only | Scope; documented deviation from the paper |
| 2026-11-13 | Of four suggested "advanced RAG" techniques: keep hybrid search + RRF; keep routing/decomposition but as a constrained router, not a free-form planner; keep verification but with deterministic numeric checks and entailment instead of model self-scoring; reject LLM-extracted GraphRAG | The alignment-derived version chains are the graph, built deterministically at no cost; LLM extraction breaks the $0 budget and is hard to defend |
| 2026-11-13 | Every retrieval component must earn a row in the ablation ladder or be cut | Stops technique-stacking from clouding what actually helps |
| 2026-11-14 | `FL_DATABASE_URL` is local Postgres; `DATABASE_URL` / `DATABASE_URL_UNPOOLED` are Neon | Tests can never touch the hosted database by accident; matches Neon's own naming |
| 2026-11-14 | Neon is used for Postgres only (project "filing lens", AWS US East 2, free plan). No object storage, functions, auth or AI gateway | Not needed; keeps the hosted footprint minimal |
| 2026-11-14 | Development uses a sample watchlist (`holdings.sample.toml`) | The author has no real holdings yet |
| 2026-11-14 | The EDGAR contact email is a request header only; the project sends no email | Clarifies there is no mail integration in any slice |
| 2026-11-15 | **Verified:** Item 1C applies to fiscal years ending on or after 2023-12-15 | SEC press release 2023-139 (release 33-11216) |
| 2026-11-15 | **Verified:** Item 9C was added by the HFCAA interim final rule effective 2021-05-05 (made final in release 34-93701). It is optional in every era and never counts toward `parse_status` | Most filers answer "Not applicable"; nothing depends on it |
| 2026-11-15 | **Verified:** SEC maximum access rate is 10 requests/second; the User-Agent format is `Name contact@email` | SEC webmaster FAQ. The 8/s cap stands |
| 2026-11-15 | **Verified:** `acceptanceDateTime` in the EDGAR submissions API is true UTC. Stored as `timestamptz`; §11.2 converts to America/New_York | AAPL 0000320193-26-000026: API `13:05:15Z`, filing index page `08:05:15` Eastern |
| 2026-11-15 | **Verified:** submissions JSON has `filings.recent` (columnar arrays incl. `accessionNumber, filingDate, reportDate, acceptanceDateTime, form, primaryDocument`) and `filings.files[]` (`name, filingCount, filingFrom, filingTo`) for older filings; `company_tickers.json` is `{"0": {"cik_str": int, "ticker": str, "title": str}, ...}` | Fetched 2026-11-15 |
| 2026-11-15 | **Verified:** FinanceBench open set is 150 rows, licence CC BY-NC 4.0; `doc_type` values seen: 10k, 10q, 8k (a fourth exists) | Hugging Face dataset card `PatronusAI/financebench` |
| 2026-11-15 | Lazy Prices four measures confirmed from a secondary source only; the primary check stays open for task 3.1 | The paper was not retrievable; slice 1 needs only cosine and Jaccard |
| 2026-11-15 | Embedding model stays `BAAI/bge-small-en-v1.5` (384-d), run with `fastembed` (ONNX Runtime), not PyTorch | Schema is fixed at 384; avoids a 2 GB torch install; local and free |
| 2026-11-15 | Slice-1 summary models: public = Gemini `gemini-3.5-flash-lite` at `https://generativelanguage.googleapis.com/v1beta/openai/` (`private_ok = false`: free-tier content is used to improve Google products); private = Groq `llama-3.3-70b-versatile` at `https://api.groq.com/openai/v1` (`private_ok = true`: Services Agreement §4.2, last modified 2026-06-22, bars training on inputs/outputs; inference requests are not retained by default). Free-tier rate limits were not verifiable from primary pages; the client uses a conservative 10 requests/minute per provider | Provider pages fetched 2026-11-15. Re-check ids and limits at tasks 1.14 and 2.2 |
| 2026-11-15 | Local Docker Postgres listens on host port **5433**, bound to 127.0.0.1. `FL_DATABASE_URL` default is `postgresql://filinglens:filinglens@localhost:5433/filinglens` | A native Postgres already occupies 5432 on the author's machine |
| 2026-11-15 | Slice-1 pipeline code uses synchronous SQLAlchemy 2 with `psycopg` 3. Async sessions are introduced with the API in slice 2 (same driver) | The pipeline is a batch CLI; sync is simpler and equally fast here |
| 2026-11-15 | Tests that need a database use a separate database `filinglens_test` on the `FL_DATABASE_URL` server, refuse any non-localhost host, and never read `DATABASE_URL` | Enforces "no test ever connects to Neon" |
| 2026-11-15 | `fiscal_year` = calendar year of `period_of_report`, minus one when that date is 1–7 January | Matches how companies label fiscal years; the January rule keeps 52/53-week filers from getting two filings in one year. Era rules use `period_of_report` dates directly |
| 2026-11-15 | `fetch_status` gains `skipped`. `10-K/A`, `10-K405/A`, `10-KT`, `10-KT/A` get manifest rows with `skipped` and are not downloaded. If a company has two original 10-Ks for one fiscal year, the earliest accepted is used and the other is excluded as `duplicate_period` | "Recorded in the manifest, excluded from pairs" made concrete |
| 2026-11-15 | Bulk discovery through `full-index/form.idx` is deferred to task 3.2. Slice 1 discovers filings through the submissions API only | Only `t2_*` universes need it |
| 2026-11-15 | Plain-text (non-HTML) primary documents get `parse_status = failed`, reason `not_html` | Slice-1 universes start at fiscal 2014; the text-era parser is the §15 expansion |
| 2026-11-15 | Block `html_offset` is realised as `source_line` (lxml's line number of the block's first element) | lxml exposes no byte offsets; the field is for debugging only |
| 2026-11-15 | **Item segmentation objective clarified (§5.4).** Each candidate heading's gain is the text between it and the *next candidate of any Item*; the DP picks the canonical-order subsequence maximising total gain. A section then runs from its chosen heading to the next *chosen* heading | Read literally, "total text between consecutive chosen headings" telescopes to the distance from the first chosen heading to the end of the document and cannot tell a table-of-contents entry from a body heading |
| 2026-11-15 | Item pattern extended to combined headings (`Items 1 and 2. Business and Properties`). All listed Items count as found; the text is stored under the first; the rest are recorded in `parse_notes.combined` | Some filers combine Items under one heading. (Exxon Mobil FY2022 and FY2023 do not; corrected 2026-11-17 after checking the fixtures) |
| 2026-11-15 | Text before the first Item is stored as paragraphs with `item = 'front'`. It is never aligned but is part of whole-document measures | Whole-document similarity (§6.4) needs the full text |
| 2026-11-15 | Item-level status: an Item is `ok` when it was found and, for Items 1, 1A, 7 and 8, has at least 2,000 characters; otherwise `short` or `missing`. An Item is aligned only when `ok` in both filings. An Item present on one side only gets a non-eligible pair row and no `added`/`deleted` edges; its paragraphs still enter the cross-Item move pool | Makes "not `ok` for the Item in question" (§5.4) concrete |
| 2026-11-15 | Normalisation order (§5.5): NFKC and lowercase, then date/year/number masking, then punctuation stripping. A number is masked only when it is not glued to a letter (`10-K`, `1A`, `COVID-19` are kept); currency sign, `%`, brackets and a following scale word (`million`, `billion`…) are part of the number | Masking after stripping cannot recognise `$1.2 billion` or `December 31, 2023` |
| 2026-11-15 | TF-IDF (§6.2) is our own implementation: tokens of `norm_masked`, unigrams + bigrams, `tf = 1 + ln(count)`, `idf = ln((1 + N) / (1 + df)) + 1`, L2-normalised. Terms are stored as 64-bit BLAKE2b hashes with `min_df = 2`; a term not in the file gets the maximum IDF (`df = 0`) instead of being dropped. Similarities are rounded to 6 decimals before any comparison | New paragraphs are made of unseen terms, so dropping them would inflate similarity; hashing keeps the file small; rounding keeps output byte-identical |
| 2026-11-15 | Aligner details (§6.3). (a) A 1-to-1 edge's label comes from the hashes: equal `exact_hash` → `unchanged`, equal `masked_hash` → `rollforward`, else `modified`, whichever stage matched it. (b) A DP match needs `sim ≥ τ`; traceback prefers "delete old", then "add new", then "match", so equal-score alignments resolve to the lowest indices. (c) Stage-1 move candidates are removed from the gaps before Stage 2 and emitted as `moved`. (d) Cross-Item `moved` edges belong to the whole-document pair row (`item` NULL). (e) Only `modified` edges can absorb a neighbour into a `split`/`merged`, one neighbour each | Each was undefined or ambiguous in §6.3 |
| 2026-11-15 | Word diff (§6.3 output): `difflib.SequenceMatcher(autojunk=False)` over `norm_exact` tokens; `changed_ratio = (n_ins + n_del) / (len_old + len_new)` | "A standard sequence diff over tokens" made concrete |
| 2026-11-15 | `alignment_pair` gains `change_intensity_raw` (computed at alignment time, cosmetic changes not removed). `change_intensity` stays NULL until the classifier has run (task 1.14) | §6.4 needs the classifier, which does not exist when task 1.8 runs |
| 2026-11-15 | Document measures use `norm_exact` unigram tokens: `sim_cosine` on raw counts, `sim_jaccard` on term sets | §6.4 did not name the tokenisation |
| 2026-11-15 | Gold alignment files and change labels identify paragraphs by `(accession, item, seq, exact_hash)`, never by database id. The evaluator fails if a hash no longer matches. Files under `eval/` are the source of truth; `change_label` rows are a cache | Database ids change when a filing is re-parsed |
| 2026-11-15 | Test fixtures are four complete public 10-Ks (Apple and Exxon Mobil, fiscal 2022 and 2023), zstd-compressed under `tests/fixtures/filings/` | Small when compressed; gives real consecutive pairs for parser and aligner tests |
| 2026-11-15 | The minimal LLM client (§10: one OpenAI-compatible client, privacy failover, disk cache, replay mode) is built at task 1.14; task 2.2 extends it | Slice-1 summaries need it |
| 2026-11-15 | Briefs for every slice-0 and slice-1 task live in `docs/briefs/`. Where a brief is more specific than this spec, the brief applies and the decision is listed here | Lead hand-over on 2026-11-16 |

### 16.1 WRDS research notes (2026-11-14, from public pages; re-check when access is granted)

- **WRDS acknowledgement** (Terms of Use, last updated 2026-08-25): "Wharton Research
  Data Services (WRDS) was used in preparing [identify research piece]. This service and
  the data available thereon constitute valuable intellectual property and trade secrets
  of WRDS and/or its third-party suppliers."
- **CRSP credit line** (as given in university library guides; confirm against CRSP's own
  terms): "Calculated (or Derived) based on data from [DATABASE NAME] ©[YYYY] Center for
  Research in Security Prices (CRSP®), The University of Chicago Booth School of Business."
- **Publishing**: the WRDS Terms do not address derived or aggregate results directly.
  The WRDS co-authorship guide says code may be shared, and that aggregated results from
  "material transformation" that cannot be reverse-engineered are acceptable to share;
  raw data may not be. A long-short portfolio return series is consistent with that
  guidance but is not explicitly named, so still confirm with WRDS Support or the library
  before publishing one. Charts and summary statistics are the safe default.
- **AI policy**: loading WRDS data into LLM tools is prohibited for most datasets. CRSP is
  listed among vendors that allow *protected* versions of such tools, with the vendor to
  be contacted for clarification. §2.3 rule 4 (no licensed rows in any AI session) stays
  as the rule.
- **Alternative route**: the U of T Map & Data Library lists CRSP as available to staff,
  faculty and students through WRDS **or CHASS (UTORid login)**. CHASS may not share the
  WRDS between-term blackout; ask the library. `CrspPriceSource` should read from local
  Parquet files so it does not care which platform the data came from.

## 17. Open items

| Item | Default until resolved | Owner |
|---|---|---|
| WRDS approval, CRSP inclusion, blackout date, permitted publication, citation wording | Unscheduled. Revisit §11.4 only if the research proposal is selected | Author → UofT library |
| Free price source for engine testing | Choose at task 3.5; any source is fine since results are not reportable | Implementer |
| Hosted Postgres and API host | Neon + whichever free container host fits the memory budget at task 2.10 | Implementer |
| Exact free-tier model ids and limits | Fill `config/models.toml` from current provider docs at task 2.2 (a summary-only entry at 1.14) | Implementer |
| Relocated Items: some filers (Exxon Mobil FY2022–2023) answer Items 7 and 8 with a one-line pointer to a Financial Section after Item 16, so the MD&A is parsed as part of Item 16 and the filing is `partial` (`short:7`, `short:8`) | Accept: Item 1A is unaffected (R1). Decide before Item 7 work (R4) whether to map a relocated section back to Items 7/8; measure how common it is in the R3 coverage run first | Lead |
| The five `t0_dev` companies and final `t1_rag` list | Select at R3 after reader review. R1 uses the demo universe | Author |

---

## 18. Resume claims this spec is built to produce

Bracketed values are filled only from recorded runs (§6.5, §7.7, §9, §11).

- Built a paragraph-level alignment engine for SEC annual reports (patience anchors +
  dynamic programming + move/split detection); [P]/[R] precision/recall on changed
  paragraphs against a hand-aligned set of [N] filing pairs, versus [baseline] for a
  standard diff.
- Built a versioned retrieval index from those alignments that stores each paragraph
  once with its validity range, cutting index size by [X]× and raising accuracy on
  multi-year questions from [A]% to [B]% in a [k]-step ablation on FinanceBench and a
  custom set.
- Classified filing changes with a from-scratch softmax model ([F1] macro-F1, grouped
  by company) to alert on substantive changes in held companies at [P]% precision.
- Reproduced the "Lazy Prices" text-change signal over [N] filings with a point-in-time
  backtest framework validated on synthetic data — *or, with CRSP:* found [result]
  after transaction costs, including after the paper's publication.
