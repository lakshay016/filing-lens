# Filing Lens — Status

Updated by whoever finishes a task. Newest entry at the top of the log.

## Now

- **Current task:** R2. Both development pairs (Apple, Microsoft FY2022→2023) pass the
  source-only extraction check under parser v4. Pages `data/r2/apple-1a.html` and
  `data/r2/msft-1a.html` are generated with the frozen comparison (`r2-freeze`) and remain
  unopened. Next: the agent-run technical pilot, or the independent reference list and
  human sessions once readers are recruited. Human reading time and usefulness are unmeasured.
- **Next design review:** after R2 reader sessions, bring per-reader times, source-linked must-see changes found and missed, and distracting alerts for both workflows. Escalate earlier if the corrections change the substantive output on the XOM example.
- **Lead:** Opus 5.5 from 2026-11-17.
- **Author setup:** done. `.env` uses port 5433 and the pre-commit guard is installed
  (2026-11-17).
- **Blockers:** none. `uv` 0.13.8 with Python 3.12.16 and Docker 29.9.3 (daemon running)
  were verified on 2026-11-15.
- **Lead:** Fable 5.2 until 2026-11-16, then Opus 5.5, working from `docs/briefs/`.

## Setup checklist

| Item | State (2026-11-15) |
|---|---|
| GitHub repo `lakshay016/filing-lens`, remote `origin` | Done |
| `.env` with `FL_SEC_USER_AGENT`, `GROQ_API_KEY`, `GEMINI_API_KEY` | Author reports done; seen in a screenshot, not verified by a script |
| `FL_DATABASE_URL` = local Docker Postgres | Author reports done |
| Neon project ("filing lens", AWS US East 2, free plan); `DATABASE_URL`, `DATABASE_URL_UNPOOLED` in `.env` | Done; not used until slice 2 |
| Homebrew | Installed |
| Python 3.12 via `uv` | Done (uv 0.13.8, CPython 3.12.16) |
| Docker running | Done (29.9.3) |
| Disk space | ~619 GB free |
| Sample watchlist `holdings.sample.toml` | Done (author has no real holdings) |
| Ollama | Skipped; optional |
| WRDS / CRSP access | Registered, not approved. Proceeding with the fallback (SPEC §11.4) |

## Open questions for the author

- Remove the Neon tooling files (`neon.ts`, `package.json`, `package-lock.json`,
  `node_modules/`)? They declare an object-storage bucket the project does not use.
  The `AWS_*` lines in `.env` belong to the same unused feature.
- Ask the U of T library whether CRSP through CHASS avoids the WRDS between-term
  blackout (SPEC §16.1). Not urgent.

## Things only the author can do (upcoming)

The first human study is R2. Arrange independent readers, collect must-see references and observe timed tasks. Later, select the broader evaluation companies and supply blind gold alignments. Classifier labels are conditional on the ranking review.

## Log

### 2026-11-18 — parser v4: repeated Item page headers
- Microsoft's bare "Item 1A" page header (14 per filing) made segmentation start Item 1A
  late while reporting `ok`. Fixed in `items.py` (running headers removed before gains,
  skipped as paragraphs); regression tests fail on the old code. Check script now finds the
  section start independently. All four R2 filings pass (lead re-ran): Apple 107/107,
  100/100; Microsoft 92/92, 82/82; 99.2–99.4% coverage; 0 unexplained. Microsoft Item 1A:
  41,678 → 69,870 and 23,738 → 68,253 chars. Apple, XOM and the fixtures are unchanged.

### 2026-11-18 — Apple extraction check passed
- `scripts/check_extraction.py` added (one filing at a time; never compares years). Apple
  FY2022: 107/107 paragraphs in order, 99.24% coverage. FY2023: 100/100, 99.27%; one
  48-character footer + sub-heading stretch, classified. 0 unexplained. Re-run by the lead.

### 2026-11-18 — pre-R2 corrections merged and frozen
- PR #15 merged: sign/unit-preserving key, §6.1 gaps, standalone counts and neutral
  unresolved groups. XOM FY2023 ¶16 now readable; ¶12 control keeps its inline marking.
  316 tests pass; CI green. Author reviewed a534e83 and kept the strict key (SPEC §16);
  four XOM punctuation-only edits now appear as changes. Tagged `r2-freeze`.
- Apple FY2022→2023 page generated at `data/r2/apple-1a.html`; not opened by anyone.

### 2026-11-17 — task 1.5 done
- Paragraphs, `norm_exact`/`norm_masked`, hashes and paragraph storage merged. 280 tests
  pass; CI green. Lead probes: number/date/year-only edits mask equal (10% → 35% customer,
  debt, headcount, reserves); word edits do not; `10-K`, `Item 7A`, `COVID-19`, `10b5-1`
  keep their digits. XOM FY2023 Item 1A: 39 paragraphs.
- Known limitations passed to brief 1.12: `Scope 1 and 2` is masked like any number; the
  scale word after `$(1.2)` is not absorbed. Brief expectation "< 5% short paragraphs"
  holds within Items 1, 1A, 7 but not whole-filing for Apple FY2023 (5.6%: "None.",
  signatures, captions); left as measured.

### 2026-11-17 — task 1.4 done
- Item segmentation, parse status and `fl parse --report` merged. The table-of-contents
  rule is tested and fails under the wrong gain definition. 174 tests pass; CI green.
- Apple FY2022/2023 parse `ok`. Exxon FY2022/2023 parse `partial` (`short:7`, `short:8`):
  Exxon's Items 7 and 8 point to a Financial Section after Item 16. Exxon Item 1A is
  correct (29,578 characters, ends at Item 1B), so R1 is unaffected. Recorded in SPEC §17;
  to be decided before Item 7 work (R4). `fl parse` has not yet run on real ingested data.
  Next: task 1.5.

### 2026-11-17 — task 1.3 done
- `extract_blocks` merged with four fixture 10-Ks (Apple and XOM, FY2022–2023). XOM FY2023
  Item 1A reads cleanly: one block per risk, group titles as headings, bullets kept.
- Review found that dash-only table cells (zeros) were dropped, shifting values into the
  wrong columns. Sent back; dashes now stay in place as `—`. 139 tests pass; CI green.
- Exxon FY2022–2023 have no combined "Items 1 and 2" heading: SPEC §16 and briefs 1.2–1.4
  corrected. In the fixtures the table of contents comes out as a table block (note added
  to brief 1.4). Next: task 1.4.

### 2026-11-17 — reader-first roadmap adopted
- R1 is ready for implementation. The R1–R5 brief records the evidence and decisions for each review.

### 2026-11-17 — task 1.2 done (code)
- Merged `fl ingest`, `fl universe check`, `fl universe draft-t1`, the filing manifest and
  zstd raw storage. Tested against mocked EDGAR only: a second run makes no download
  requests; amendments are `skipped`; a 404 becomes `failed` and is retried next run.
  100 tests pass; CI green. No real download has been made yet.
- Accepted, not fixed (small follow-ups): a company whose filing list fails after all
  retries stops the whole ingest (re-running resumes); `primary_document` from SEC is used
  unchecked as a file name. The FinanceBench raw-file URL in `edgar/cli.py` has not been
  fetched yet; `draft-t1` exercises it first.

### 2026-11-17 — task 1.1 done
- EDGAR client merged: shared 8 requests/second token bucket (retries included), backoff
  with jitter on 429/403/5xx/timeouts, `Retry-After` honoured, only `https` to
  `www.sec.gov`/`data.sec.gov`, the User-Agent is never logged or put in errors.
- Review found that 3xx responses were returned as success (a redirect page would have
  been stored as a filing). Sent back; now only 2xx is success and redirects are not
  followed, with tests for 301/302/304. 53 tests pass; CI green.

### 2026-11-15 — briefs complete
- `docs/briefs/` now has one brief for every task of slices 0 and 1 (0.1–0.4, 1.1–1.16)
  plus `README.md` (agent rules, module ownership, lead protocol).

### 2026-11-15 — task 0.4 done, slice 0 complete
- CI merged: guard, ruff, mypy, migration and pytest (32 passed, database tests not
  skipped) run on every pull request in about 30 seconds.

### 2026-11-15 — task 0.2 done
- Local Postgres (pgvector, port 5433), models and migration `0001` merged. Upgrade,
  downgrade and `alembic check` are clean; 7 database tests pass; migrating a non-local
  host is refused. The compose project is named `filinglens` so the container and volume
  do not depend on the checkout directory.

### 2026-11-15 — task 0.3 done
- Licensed-data guard merged: a planted `.parquet` makes it exit 1 (checked by hand and
  in tests). `.env.example` now uses port 5433. The pre-commit hook is in `.githooks/`
  but is **not installed** yet: the author runs `sh scripts/install_hooks.sh` once.

### 2026-11-15 — task 0.1 done
- Project skeleton merged: `uv run fl --help` works, 13 tests pass, ruff and mypy clean.
  `fl env` shows which settings are filled in without printing any value.

### 2026-11-15 (later)
- Branch `docs/briefs` (not merged): SPEC §16 has the verified facts and design decisions
  dated 2026-11-15; `docs/briefs/` has README (conventions, lead protocol) and briefs
  0.1, 0.2, 0.3, 0.4, 1.7, 1.8. **Briefs still to write:** 1.1–1.6, 1.9–1.16; the
  decisions they need are already in SPEC §16. No task has been dispatched; next is
  finish the briefs, merge this branch, then task 0.1.
- Found: a native Postgres listens on 5432, so Docker Postgres uses port 5433. The
  author must change the port in `FL_DATABASE_URL` in `.env` to 5433.

### 2026-11-15
- uv and Docker blockers cleared and verified. Docs committed to `main`.

### 2026-11-14
- Researched WRDS terms, citation wording and AI policy from public pages; recorded in
  SPEC §16.1. Found CRSP is also listed as available through CHASS at U of T.
- Added `docs/PRODUCT.md`, `docs/STATUS.md`, `CLAUDE.md`, `docs/MANAGER_PROMPT.md`,
  `holdings.sample.toml`; tidied `.env.example`.
- Environment naming settled: `FL_DATABASE_URL` local, `DATABASE_URL` Neon.

### 2026-11-13
- Original eight-component plan reviewed and pivoted to one alignment engine driving
  alerts, retrieval and research. `SPEC.md` written.
