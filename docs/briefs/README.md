# Briefs — how to use them

One brief per task in SPEC §14, slices 0 and 1. A brief is written so that a model that
has seen nothing else can do the task. This file holds what every brief shares; each
brief starts by pointing here.

Written 2026-11-15 by the outgoing lead. Decisions made while writing the briefs are
recorded in SPEC §16 (rows dated 2026-11-15). Where a brief is more specific than the
spec, the brief applies within its selected component. SPEC §14 and the [reader-first brief](reader-first.md) govern scheduling, scope and release evaluation.

## Part A — rules for the implementing agent

Read `CLAUDE.md` first. The points that agents most often break:

1. **Do only your task.** Create or change only the files your brief lists. If you think
   another file must change, stop and say so in your report.
2. **Do not touch** `TODO.md`, `docs/STATUS.md`, `SPEC.md`, `docs/briefs/`, `neon.ts`,
   `package.json`, `package-lock.json`, `node_modules/`, `.neon`, `.claude/`, `.env`.
   The lead updates TODO and STATUS on your branch after review.
3. **Secrets.** Never read, print, log or echo `.env` or any value from it. Code reads
   settings through `filinglens.config.get_settings()`. To check a variable, test only
   whether it is set.
4. **No network in tests.** EDGAR is mocked with `respx`. LLM calls run with
   `FL_LLM_MODE=replay`. A test that opens a socket to anything but local Postgres is a
   bug.
5. **Database.** Local Docker Postgres only, on port **5433**:
   `postgresql://filinglens:filinglens@localhost:5433/filinglens`. These are public
   defaults from `.env.example`, not secrets. Until the author updates `.env`, prefix
   commands that need the database with
   `FL_DATABASE_URL=postgresql://filinglens:filinglens@localhost:5433/filinglens`.
   Never use `DATABASE_URL` or `DATABASE_URL_UNPOOLED` (hosted Neon).
6. **Never** open or list anything under `FL_LICENSED_DIR` (`~/filinglens-licensed`).
7. **Cost is $0.** No paid API, no paid service.
8. **Never fabricate labels, gold alignments or judgements.** Build the tool and stop.
9. **Git.** Work on the branch named in the brief, cut from up-to-date `main`. Small
   commits at working milestones. Commit messages are plain imperative sentences with
   **no AI attribution** (no `Co-Authored-By`, no "Generated with"). Push the branch and
   open a pull request into `main` with `gh pr create`; the PR body has no attribution
   line either. Do not merge it.
10. **Everything runs through uv**: `uv run ...`, `uv add ...`, `uv add --dev ...`.
11. **Report honestly.** Your final message states: what you built, the exact commands
    you ran for the checks below and their output, anything that failed or that you
    skipped, and any decision you made that the brief did not cover.

Checks that must pass before you open the PR (once the tools exist, from task 0.1 on):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

### Conventions

- Python 3.12, `src/` layout, package `filinglens`. Type hints on every function.
  Dataclasses are `frozen=True, slots=True` unless the brief says otherwise.
- `mypy` is strict for `filinglens.align` (and later `filinglens.backtest`), standard
  elsewhere.
- Logging: `logging.getLogger(__name__)`. No `print` outside `cli.py` modules.
- CLI: `typer`. Each package exposes a `typer.Typer()` in its own `cli.py`
  (`filinglens/edgar/cli.py` and so on); the root `filinglens/cli.py` registers it with
  one `app.add_typer(...)` line. Adding that one line to the root file is always allowed.
- Version constants live in `filinglens/versions.py`: `PARSER_VERSION`,
  `ALIGNER_VERSION`, `IDF_VERSION`, `CLASSIFIER_VERSION`. Bump the constant when the
  output of that stage can change; every derived row stores it.
- Tests: `tests/unit/` (no database, no files outside `tests/fixtures/`),
  `tests/integration/` (may use the database; mark with `@pytest.mark.db`). Database
  tests use the `db_session` fixture from `tests/conftest.py`, which works on a separate
  database named `filinglens_test`.
- Snapshot tests use the helper `tests/snapshot.py` (`assert_snapshot(name, obj)`); set
  `FL_UPDATE_SNAPSHOTS=1` to rewrite. A snapshot change must be explained in the PR.
- Banned file types anywhere in the repo: `*.parquet`, `*.csv`, `*.sas7bdat`, `*.dta`.
  Fixtures are JSON, JSONL, TOML, HTML, or zstd-compressed HTML.
- Paths: runtime data goes under `get_settings().data_dir` (`./data`, gitignored).

### Shared vocabulary

| Term | Meaning |
|---|---|
| filing | One 10-K. Identified by `accession` (with dashes, `0000320193-23-000106`) |
| Item | A 10-K section code: `1, 1A, 1B, 1C, 2, 3, 4, 5, 6, 7, 7A, 8, 9, 9A, 9B, 9C, 10 … 16`, plus `front` |
| block | Output of HTML extraction: `text`, `table` or `heading` |
| paragraph | One `text` or `table` block inside an Item; the alignment unit |
| pair | Two consecutive annual reports of one company: old `A`, new `B` |
| edge | One alignment result linking 0–2 old paragraphs to 0–2 new ones, with a label |

## Part B — module ownership

| Path | Created by task |
|---|---|
| `pyproject.toml`, `src/filinglens/{__init__,cli,config,versions}.py`, `tests/conftest.py`, `tests/snapshot.py` | 0.1 |
| `docker-compose.yml`, `alembic.ini`, `migrations/`, `src/filinglens/db/` | 0.2 |
| `.env.example`, `.gitignore`, `scripts/check_licensed_data.py`, `.githooks/` | 0.3 |
| `.github/workflows/ci.yml` | 0.4 |
| `src/filinglens/edgar/client.py` | 1.1 |
| `src/filinglens/edgar/{index,fetch,store,universe,cli}.py`, `config/universes/` | 1.2 |
| `src/filinglens/parse/html.py`, `tests/fixtures/filings/` | 1.3 |
| `src/filinglens/parse/{items,cli,pipeline}.py` | 1.4 |
| `src/filinglens/parse/{normalize,paragraphs}.py` | 1.5 |
| `docs/RESULTS.md`, `src/filinglens/report.py` | 1.6 |
| `src/filinglens/align/{types,tfidf,anchors,dp,diff,engine}.py` | 1.7 |
| `src/filinglens/align/{moves,splitmerge,measures,store,cli}.py` | 1.8 |
| `tools/labeler/`, `src/filinglens/evalalign/{gold,sample}.py` | 1.9 |
| `src/filinglens/evalalign/{metrics,baselines,run,cli}.py` | 1.10, 1.11 |
| `src/filinglens/changes/{boilerplate,numeric}.py` | 1.12 |
| `src/filinglens/changes/{features,softmax,embed,labels,train,cli}.py` | 1.13 |
| `src/filinglens/changes/rank.py`, `src/filinglens/llm/`, `src/filinglens/watch/`, `config/models.toml` | 1.14 |
| `src/filinglens/changes/alert_eval.py` | 1.15 |
| `README.md` | 1.16 |

`evalalign` is the code package for alignment evaluation; data and results stay under
`eval/alignment/` as the spec lays out.

## Part C — for the lead

### Order and parallelism

Start with R1 in the [reader-first brief](reader-first.md). Task numbers 1.3–1.16 identify reusable component designs. Dispatch only the portions selected for the current milestone. Review the baseline before reader sessions, reader findings before algorithm selection, development results before the held-out run, and release evidence before history or Q&A work. Refresh a component brief's dependencies and acceptance checks when a review activates it.

### Models

| Tasks | Model | Why |
|---|---|---|
| 0.1–0.4, 1.1, 1.2, 1.3, 1.5, 1.6, 1.9, 1.14, 1.16 | Sonnet | Scaffolding, plumbing, parsers with fixture tests, CLI wiring |
| 1.4 | Sonnet, with careful review of the DP | Small DP with a known trap (see the brief) |
| 1.7, 1.8, 1.10, 1.11 | Opus | Alignment engine and its evaluation: correctness is the claim |
| 1.12, 1.13, 1.15 | Opus for `softmax.py`, `numeric.py` and the metric code; Sonnet for the rest | Numbers on the resume come from these |

### Dispatch

Give the agent this and nothing else:

> You are implementing task N.M of Filing Lens in the repository at the current
> directory. Read `CLAUDE.md`, then `docs/briefs/README.md` Part A, then
> `docs/briefs/<file>` and the SPEC sections it names. Do exactly that brief. Finish
> with the report described in README Part A point 11.

### Review (never skip; an agent's report is not proof)

1. `git fetch && git checkout <branch>`; read the whole diff against `main`.
2. Run the four checks yourself, then the brief's "Done when" command. Read the output.
3. Check the diff touches only the files the brief lists and adds no attribution lines
   (`git log main..HEAD --format=%B | grep -i -E "co-authored|generated with"` is empty).
4. Work through the brief's "Review checklist" line by line.
5. Wrong work goes back to the same agent with specific corrections. Fix it yourself
   only when it is a one-line change.
6. When it passes: on the same branch tick the task in `TODO.md`, update
   `docs/STATUS.md` ("Now" and a log entry), push, wait for CI to go green, merge the
   PR (`gh pr merge --merge --delete-branch`), then `git checkout main && git pull`.
7. Report to the author: what was built, the acceptance result, anything failed or
   skipped, what is next.

### Stops for the author

Tasks marked `[you]` in `TODO.md`. Build the tool, give exact instructions, wait. Each
brief that ends in an author step has a section "Hand-over to the author" with the
instructions to give. Do not start slice 2 without asking. If a spec decision looks
wrong, say what you would change and why before changing it, then record it in §16.

### Things a new lead is most likely to get wrong

- **Item segmentation (1.4):** the gain of a candidate heading is the text up to the
  next *candidate*, not the next *chosen* heading. The second version looks right and
  silently picks table-of-contents entries.
- **Aligner (1.7/1.8):** read `1.7-aligner-anchors-dp.md` section "Traps" before
  reviewing. The usual failures are: anchors taken from non-unique hashes; matching at
  `sim < τ`; dropping out-of-vocabulary terms in TF-IDF; a paragraph ending up in two
  edges after Stage 3 or 4; non-deterministic tie-breaks from iterating a `set`.
- **Gold data (1.9):** the labelling tool may pre-fill exact-hash matches only. Any
  suggestion that comes from the aligner or from TF-IDF similarity contaminates the
  evaluation.
- **Test split (1.11):** scored once. The command refuses a second run. Do not tune
  anything after looking at it.
- **Splits by company:** classifier cross-validation groups by CIK (1.13); alert
  evaluation uses companies the classifier never saw (1.15).
- **`.env` port:** if a command reports a database authentication error on port 5432,
  the author has not yet changed `FL_DATABASE_URL` to port 5433.
