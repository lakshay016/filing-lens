# Filing Lens — Status

Updated by whoever finishes a task. Newest entry at the top of the log.

## Now

- **Phase:** **slice 0 complete** (0.1–0.4 merged, CI green). Next task: **slice 1, task 1.1**
  (EDGAR client). Briefs for every slice-1 task are in `docs/briefs/`.
- **Author actions outstanding:** change the port in `FL_DATABASE_URL` in `.env` to 5433;
  run `sh scripts/install_hooks.sh` once to install the pre-commit guard.
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

Marked `[you]` in TODO.md. In slice 1: choose the five development companies (1.2),
hand-align 10 then 20 filing pairs (1.9, 1.11), label about 100–300 changes (1.13),
judge 100 alerts and do the one-week relabel (1.15). Roughly 15–25 hours in total.

## Log

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
