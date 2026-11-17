# Filing Lens — instructions for any agent working in this repo

## Read first

1. [docs/STATUS.md](docs/STATUS.md) — where things stand and what is next.
2. [docs/PRODUCT.md](docs/PRODUCT.md) — what the product is, restrictions and limitations.
3. [SPEC.md](SPEC.md) — the technical design. It is the source of truth.
4. [TODO.md](TODO.md) — active milestone checklist.
5. [docs/briefs/reader-first.md](docs/briefs/reader-first.md) — implementation steps and when to return to the lead. SPEC §14 sets the delivery order for all component briefs.

## Rules that are never broken

- **Follow the spec.** Statements in SPEC.md are decisions. Do not redesign. If a
  decision proves wrong, stop, explain why, and record the change in SPEC §16.
- **`[VERIFY]` items** were recalled from memory. Check them against the primary
  source before code depends on them, then remove the tag and note it in §16.
- **Secrets.** Never print, log, echo or commit values from `.env`. Check only that a
  variable is set. Never ask the author to paste a key into chat.
- **Licensed data.** Never open, read, load or list anything under `FL_LICENSED_DIR`,
  and never work in a session where CRSP or WRDS files are readable. Code for licensed
  data is written against the documented schema and synthetic fixtures only; the
  author runs it (SPEC §2.3, §11.6).
- **No data files in the repo.** `data/`, `*.parquet`, `*.sas7bdat`, `*.dta`,
  `holdings.local.toml` are ignored and stay that way.
- **Databases.** Development and tests use `FL_DATABASE_URL` (local Docker Postgres).
  `DATABASE_URL` / `DATABASE_URL_UNPOOLED` are the hosted Neon database and are not
  touched before slice 2. No test ever connects to Neon.
- **Network in tests.** None. EDGAR is mocked; LLM calls run in replay mode.
- **SEC fair access.** At most 8 requests/second, with the `FL_SEC_USER_AGENT` header.
- **Cost.** $0. No paid API calls, no paid services, without the author's say-so.
- **Free-data backtest returns are never reported** anywhere (SPEC §11.4).
- **Human-only work stays human.** Hand-aligning filing pairs, labelling changes,
  writing the custom question set and judging answers are the author's tasks (marked
  `[you]` in TODO.md). An agent builds the tool and stops; it never fabricates labels.
- **Every number in a README, write-up or resume line comes from a recorded run.**

## Workflow

- Python 3.12 managed with `uv`; run everything through `uv run`.
- Feature branch per task (`slice1/1.3-html-blocks`), pull request into `main`.
- Small commits at working milestones. **No AI attribution lines** in commit messages
  or pull-request descriptions (no `Co-Authored-By`, no "Generated with").
- A task is done when its "Done when" check in SPEC §14 passes, tests are green, and
  TODO.md and docs/STATUS.md are updated in the same pull request.
- Report honestly: if a check fails or a step was skipped, say so with the output.

## Working as a manager with delegated agents

- The manager plans, briefs, reviews and integrates. Cheaper agents write the code.
- One writer per set of files at a time. Parallel agents only on tasks that touch
  different files and do not depend on each other.
- A brief names: the task number, the SPEC sections to read, the files to create or
  change, the acceptance check, and what not to touch. Agents do not see this
  conversation; the brief must stand alone.
- The manager verifies every result itself (reads the diff, runs the tests) before
  marking a task done. An agent's report is not proof.
- Suggested split: correctness-critical algorithms (the aligner §6, the backtest
  engine §11.5, verification §8.6) go to a stronger model and get line-by-line review;
  scaffolding, plumbing, parsers with fixture tests and CLI wiring go to a cheaper one.

## Files that are not part of the design

`neon.ts`, `package.json`, `package-lock.json`, `node_modules/` and `.neon` were created
by Neon's setup tooling. The project uses only Neon's Postgres, from slice 2. Leave
these alone unless the author asks; do not build on them.
