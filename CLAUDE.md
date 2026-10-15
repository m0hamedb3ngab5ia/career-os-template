# career-os — working rules for Claude

Job-search automation for one person, "the candidate". Architecture: always read `ARCHITECTURE.md` `## Principles` + its heading index (`rg -n '^## ' ARCHITECTURE.md`); read other sections only when task touches them (e.g. runs, QA, credentials, retention, company policy). `TODO.md`: read only when picking new work.
Candidate name/facts only from `profile/master.yaml: identity`; never hardcode.
Personal context (who candidate is, where private files live): gitignored `CLAUDE.local.md`; read if present, never copy into committed files.

## Hard rules
- Never fabricate résumé facts. Only `profile/master.yaml` bullets by id; numbers frozen; placeholder bullets never used.
- Never guess legal/EEO/salary answers: `profile/standard_answers.yaml` or Action Item.
- Never automate LinkedIn actions. Draft only.
- Never click submit twice. Never submit Tier A. Never bypass `qa-review`.
- No Anthropic API key in repo. LLM work = Claude Code skills (`claude -p` headless ok).
- Uncertain → `careeros action add` (Action Items tab), not guess.
- Never commit personal data. Gitignored: `profile/`, `config/`, `CLAUDE.local.md`, `data/`, `.reviews/`. Committed examples use fictional candidate in `examples/`. Terms in `profile/confidential_terms.yaml` never appear in any artifact or committed file.

## Setup
- `python3 -m venv .venv && .venv/bin/pip install -e ".[test]"`
- `.venv/bin/careeros init` copies `examples/{profile,config}` → `profile/`, `config/` (never overwrites); `careeros init --link <private-dir>` symlinks them (+ `CLAUDE.local.md`) from private repo. Other commands exit "run `careeros init`" until then.
- `.venv/bin/careeros doctor [--quiet]`: setup checklist, exit 1 on FAIL (example data left, broken YAML, unknown bullet_priority ids, no `claude`). `prepare-job` / `apply-job` run it first. New user: `docs/GETTING_STARTED.md`.

## Commands
Full CLI + API reference (subcommands, flags, exit codes, endpoints): `docs/COMMANDS.md`. Read before running or changing any `careeros` command or `/api` route. Most used:
- `.venv/bin/careeros doctor`, `ui [--no-open]`, `scout --sync`, `jobs list`, `run list|show <id>`
- `.venv/bin/python -m pytest -q`

## Skills (`.claude/skills/`)
`prepare-job` (score-job → tailor-resume → write-cover-letter → qa-review) · `review-resume` · `edit-resume` · `apply-job` (Chrome) · `extract-master` (master résumé → `careeros resume propose-master` → pending master.yaml diff; approve/reject `POST /api/profile/master/proposal/approve|reject`) · `answer-question` · `inbox-sync` · `find-contacts` · `draft-outreach` · `learn-voice`

## Gotchas
- `.venv` in iCloud-synced folder gets macOS hidden flag + "* 2.py" duplicates; keep checkout outside iCloud. `import careeros` breaks → `chflags -R nohidden .venv` or `PYTHONPATH=src`.
- Worktree: shared `.venv` imports another checkout's `src/`; prefix pytest + openapi regen with `PYTHONPATH=src`.
- Tracker default `data/JobTracker.xlsx` (override `config/pipeline.yaml: paths.tracker_xlsx`). Write only via `careeros.tracker.Tracker` or `careeros` CLI (atomic). Excel has it open → ops queue to `.pending.json`; `careeros tracker flush`.
- `data/` gitignored; regenerable via scout.
- `profile/voice/samples/` empty until candidate adds samples → cover letters `voice_verified: false`.

## Testing (TDD), required for every code PR
- Red → green → refactor. Failing test first, same PR as fix/feature. Bug fix = repro test first.
- Unit tests (`@pytest.mark.unit`, pure, fakes for IO) always; integration (`@pytest.mark.integration`, `tests/integration/`) when crossing a boundary: CLI via subprocess on temp repo root, scout → store → tracker with recorded HTTP fixtures, render.py → real PDF, qa over full job dir, applier vs `examples/profile/`.
- Tests read only repo (`examples/`, `tests/fixtures/`) + tmp; never `profile/`, `config/`, `data/`, `$HOME` (CI has none). No network (recorded fixtures). LaTeX tests `skipif` no engine.
- Exempt: SKILL.md-only / docs-only PRs. Python a skill calls is not exempt.
- Run: `.venv/bin/python -m pytest -q` (all), `-m unit`, `-m integration`. CI runs both unit and integration on every PR. Parallel (`-n auto` in addopts); one test / debugger: `.venv/bin/python -m pytest -n0 tests/x.py::t`. While coding: touched tests only (path / `-k`).
- Before pushing code PR: full `pytest -q` locally; CI full suite is gate. Never `gh pr merge --auto` before `/review` is clean (`None.` or findings accepted); merging is the lead's call, not a builder agent's. Before merging private sync PR: full `pytest -q` locally.
- CI shards PR runs (`CAREEROS_TEST_SHARD`/`CAREEROS_TEST_SHARDS`, hash of node ID, `tests/conftest.py`); required `pytest` check aggregates. Reproduce a shard locally with same env vars.

## Git / PR workflow
- Never push to `main`. One branch per change (`feat/…`, `fix/…`, `docs/…`); `gh pr create`. Stacked PRs ok: `--base` = parent branch; GitHub retargets children on parent merge.
- Review: `/review <PR>` (Claude + Codex parallel, merged findings; `--post` comments). Merge only after `None.` or findings consciously accepted.
- `--admin` can't skip protection: after review, wait for `pytest`, then `gh pr merge --squash` (or `--auto`).
- UI bundle conflicts: never hand-merge `src/careeros/ui/static/`; `git checkout origin/main -- src/careeros/ui/static`, rebuild, update UI snapshots. Merge UI PRs one at a time.

## Response format
Reply finishing work ends with `**Next:**`: top 3–5 concrete steps, split "you" (inputs/decisions candidate owes) / "me" (what I do on go-ahead).

## Learning
Evidence `.agent/LESSONS.md`, decisions `.agent/DECISIONS.md`: search, don't load whole. Record/promote per `~/.agent-learning/PROTOCOL.md` (or the `learn` skill). Promoted rules go here; AGENTS.md points here.

## Product system (`/product`; how-to `docs/product/README.md`)
Any task touching product behaviour:
- Read `docs/product/STATUS.md` first. Scope reads via `~/.claude/skills/product/scripts/trace.py ids <ID>`; don't load all docs.
- Bug → Fix lane (failing test first). Feature → `/product new`. Never change REQ/SCOPE/acceptance silently: `/product change <ID>`.
- UI work: apply `~/.claude/skills/product/UI_UX_PRINCIPLES.md` (P1–P20, verification checklist).
- Missing requirement / UX / design detail → `docs/product/OPEN_QUESTIONS.md` + ask; don't invent.
- PR body: `Implements: REQ-… UC-…` / `Verification: E2E-…`. Status `verified` only via `/product verify`.

## Work docs
Stream = `docs/work/<slug>/` (README Brief+Status, `handoffs/YYYY-MM-DD-NN.md` (versioned, never deleted)); fresh agent reads README + newest handoff only. Branch `work/<slug>`. Requirements stay in `docs/product/` (link IDs). Map `~/Code/WORK.md` (`/docs`).
