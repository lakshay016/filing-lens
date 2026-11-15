# Filing Lens TODO

Task numbers match SPEC.md §14. `[you]` = only the author can do it.

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
- [ ] 0.4 GitHub Actions: lint + tests

## Slice 1 - alignment engine and change alerts (~3-4 weeks)
- [ ] 1.1 EDGAR client: token bucket, retries, User-Agent check
- [ ] 1.2 Index + manifest + fetcher; `fl ingest`
- [ ] [you] 1.2 Pick the five `t0_dev` companies and final `t1_rag` list
- [ ] 1.3 HTML -> blocks
- [ ] 1.4 Item segmentation + parse status + `fl parse --report` (>= 90% ok)
- [ ] 1.5 Paragraphs + normalisation + hashes
- [ ] 1.6 Ingest and parse `t1_rag`; coverage table in `docs/RESULTS.md`
- [ ] 1.7 IDF fit; aligner stages 1-2
- [ ] 1.8 Aligner stages 3-4; document measures
- [ ] [you] 1.9 Labelling tool; hand-align 10 dev pairs
- [ ] 1.10 Tune tau on dev; baselines; `fl eval alignment`
- [ ] [you] 1.11 Hand-align 20 test pairs; single test run
- [ ] 1.12 Boilerplate shingles; numeric-delta check
- [ ] [you] 1.13 Label 100 seed edges, then active-learning batches; classifier
- [ ] 1.14 Alert ranking, LLM summaries, `fl watch`, `fl backfill`, digest
- [ ] [you] 1.15 Alert precision judgements; kappa relabel pass (>= 7 days after 1.13)
- [ ] 1.16 README with method, results, limitations

## Slice 2 - temporal RAG and evaluation (~4 weeks)
- [ ] [you] Free hosted Postgres with pgvector (Neon); free container host for the API; Vercel
- [ ] 2.1 Version chains from edges; dedup ratio
- [ ] 2.2 LLM layer: cache, replay mode, privacy tags; fill `config/models.toml` from current provider docs
- [ ] 2.3 Eval harness, FinanceBench download + accession mapping, A0 baseline
- [ ] [you] 2.4 Own 60-question set + route labels
- [ ] 2.5 Own BM25; dense index; RRF (A1, A2)
- [ ] 2.6 Reranker (A3)
- [ ] 2.7 XBRL fact loader, concept map, formula registry, router (A4)
- [ ] 2.8 Decomposition (A5); verification + retry (A6)
- [ ] [you] 2.9 Judge calibration: label 60 answers
- [ ] 2.10 FastAPI + Next.js UI + caps; deploy
- [ ] 2.11 Thin MCP server; smoke eval in CI

## Slice 3 - research track (~2-3 weeks, can overlap slice 2)
- [ ] 3.1 Read the paper; resolve `[VERIFY]` items; update decision log
- [ ] 3.2 `t2_lite` ingest and signal build
- [ ] 3.3 `PriceSource` protocol + `SyntheticPriceSource`
- [ ] 3.4 Backtest engine + the five tests of §11.5
- [ ] 3.5 `FreePriceSource`; end-to-end run; not-reportable enforcement
- [ ] 3.6 Write-up (`docs/WRITEUP.md`)
- [ ] 3.7 CRSP expansion when the gate clears
