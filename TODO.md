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
- [ ] R1 Build parser tasks 1.3–1.5 in full (1.3 done); ingest XOM FY2021–2023, extract and verify Item 1A, generate both baseline comparisons, document errors, and verify reproducibility.
- [ ] **Return for technical review** with the HTML and R1 note before expanding the parser or starting advanced alignment.
- [ ] R2 [you] Arrange reader sessions and independent must-see references. Record time, misses and distracting alerts for each workflow.
- [ ] Review reader evidence and select the next engineering change.
- [ ] R3 Choose broader dev/test company sets and run the coverage task 1.6 and the applicable parts of 1.7–1.10. [you] Produce blind gold alignments. Review dev results before freeze, then score the 1.11 test set once.
- [ ] R4 Add Item 7, deterministic ranking and numeric evidence. Evaluate all displayed alerts, must-see recovery and reading time on unseen companies. [you] Arrange independent human judgments.
- [ ] Review digest results and publish the first portfolio release with measured limitations.
- [ ] R5 If selected, test paragraph history against period-filtered search. Review paired results before extending Q&A.

## Deferred work

Classifier training and relabeling (1.13), automated summaries, hosted chat and MCP require a later design decision. The research track (§11) has no scheduled implementation or data-access dependency for the portfolio release.
