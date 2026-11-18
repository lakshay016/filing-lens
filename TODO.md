# Filing Lens TODO

Milestones R1–R5 follow SPEC.md §14. Older task numbers identify component briefs. `[you]` = only the author can do it.

## Setup (before slice 1)
- [x] [you] Fill in `.env`: EDGAR contact string (`FL_SEC_USER_AGENT`)
- [x] [you] Groq API key (free account) -> `GROQ_API_KEY`
- [x] [you] Gemini API key (Google AI Studio) -> `GEMINI_API_KEY`
- [x] Watchlist: sample in `holdings.sample.toml` (no real holdings yet)
- [x] [you] Neon project created; `DATABASE_URL` in `.env` (unused until slice 2)
- [x] Disk space: ~619 GB free
- [x] WRDS terms, citation and AI policy researched (SPEC §16.1)
- [x] [you] Install uv: `brew install uv`, then `uv python install 3.12` (verified 2026-11-15)
- [x] [you] Start Docker Desktop (verified running 2026-11-15)
- [ ] [you] Decide whether to remove Neon tooling files (`neon.ts`, `package.json`, `node_modules/`)
- [ ] [you] Optional: ask the UofT library whether CRSP via CHASS avoids the WRDS blackout

## Slice 0 - skeleton (~2 days)
- [x] 0.1 `pyproject.toml`, uv, Python 3.12, `src/` layout, ruff, pytest, `fl` CLI stub
- [x] 0.2 `docker-compose.yml` (Postgres + pgvector); Alembic initial migration
- [x] 0.3 `.env.example`, `.gitignore` for `data/`, licensed-data guard hook
- [x] 0.4 GitHub Actions: lint + tests

## Active development plan

Use the [implementation and review brief](docs/briefs/reader-first.md) for acceptance checks and handoff contents. Tick a review after recording its decision in SPEC §16.

- [x] 1.1 EDGAR client and 1.2 ingest implementation merged. The broader universe run is outstanding.
- [x] R1 parser tasks 1.3–1.5 built in full.
- [x] R1 XOM comparison generated and independently reproduced from the review branch. Both pairs' HTML matched after excluding run metadata.
- [x] R1 technical review completed. Preserve the original baseline for comparison.
- [x] Before timed R2 sessions, make three corrections on the R1 implementation and regenerate the reader packet (PR #15, frozen at tag `r2-freeze`; strict key kept, 2026-11-18):
  1. Use a comparison key that retains financially meaningful signs, units and comparators. Test a sign reversal, a currency change and a formatting-only whitespace change.
  2. Check §6.1 eligibility before building each pair. A missing intervening filing must produce an explicit gap and no annual comparison across it.
  3. Label counts as standalone additions/removals and explain that changed groups can contain new or removed passages. In unresolved groups, display readable earlier/later text without whole-paragraph strikethrough. Retain inline changes for 1×1 groups. Verify with FY2023 ¶16 and the FY2023 ¶12 control.
- [x] Apple FY2022→2023 Item 1A extraction completeness check (source-only: body heading, ordered interior text reconciled with the raw filing, unexplained gaps reported). Passed 2026-11-18 (`scripts/check_extraction.py`; 107/107 and 100/100 paragraphs in order, 99.2–99.3% coverage, 0 unexplained).
- [ ] Prepare two fresh Item 1A development pairs for R2 (Apple page generated; second pair waits for the reader's company). Start with Apple FY2022→2023 (existing fixtures) and a second, comparably sized pair from the reader's coverage. Check both sections, reserve both companies for development and freeze the independent reader's reference list before sessions. XOM is the walkthrough only.
- [ ] R2 [you] Arrange reader sessions and independent must-see references. Record time, misses and distracting alerts for each workflow.
- [ ] Review reader evidence and select the next engineering change.
- [ ] R3 Choose broader dev/test company sets and run the coverage task 1.6 and the applicable parts of 1.7–1.10. [you] Produce blind gold alignments. Review dev results before freeze, then score the 1.11 test set once.
- [ ] R4 Add Item 7, deterministic ranking and numeric evidence. Evaluate all displayed alerts, must-see recovery and reading time on unseen companies. [you] Arrange independent human judgments.
- [ ] Review digest results and publish the first portfolio release with measured limitations.
- [ ] R5 If selected, test paragraph history against period-filtered search. Review paired results before extending Q&A.

## Deferred work

Classifier training and relabeling (1.13), automated summaries, hosted chat and MCP require a later design decision. The research track (§11) has no scheduled implementation or data-access dependency for the portfolio release.
