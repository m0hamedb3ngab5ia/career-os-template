# career-os — working rules for Claude

Job-search automation for one person, "the candidate". Read `ARCHITECTURE.md` first, then `TODO.md`.
The candidate's name and facts come only from `profile/master.yaml: identity` (never hardcode them).
Personal context (who the candidate is, where their private files live) lives in the gitignored
`CLAUDE.local.md`; read it when present, never copy it into committed files.

## Hard rules
- Never fabricate résumé facts. Only `profile/master.yaml` bullets by id; numbers frozen. Placeholder bullets never used.
- Never guess legal/EEO/salary answers. `profile/standard_answers.yaml` or Action Item.
- Never automate LinkedIn actions. Draft only.
- Never click submit twice. Never submit Tier A. Never bypass `qa-review`.
- No Anthropic API key in this repo. LLM work = Claude Code skills (`claude -p` headless ok).
- Uncertain → `careeros action add` (Action Items tab), not a guess.
- Never commit personal data. `profile/`, `config/`, `CLAUDE.local.md`, `data/`, `.reviews/` are gitignored;
  committed examples use the fictional candidate in `examples/`. Terms in `profile/confidential_terms.yaml`
  never appear in any artifact or committed file.

## Setup
- `python3 -m venv .venv && .venv/bin/pip install -e ".[test]"`
- `.venv/bin/careeros init` copies `examples/{profile,config}` → `profile/`, `config/` (never overwrites);
  `careeros init --link <private-dir>` symlinks them (and `CLAUDE.local.md`) from the candidate's private repo.
  Every other command exits with "run `careeros init`" until then.
- `.venv/bin/careeros doctor [--quiet]` — setup checklist (exit 1 on FAIL: example data left, broken YAML, unknown
  bullet_priority ids, no `claude`). `prepare-job` / `apply-job` run it first. New-user walkthrough: `docs/GETTING_STARTED.md`.

## Commands
Full CLI + API reference (every `careeros` subcommand, flags, exit codes, endpoints): `docs/COMMANDS.md`.
Read it before running or changing any `careeros` command or `/api` route. Most used:
- `.venv/bin/careeros doctor`, `ui [--no-open]`, `scout --sync`, `jobs list`, `run list|show <id>`
- `.venv/bin/python -m pytest -q`

## Skills (`.claude/skills/`)
`prepare-job` (orchestrates score-job → tailor-resume → write-cover-letter → qa-review) · `review-resume` · `edit-resume` · `apply-job` (Chrome) · `extract-master` (master résumé → `careeros resume propose-master` → pending master.yaml diff; approve/reject `POST /api/profile/master/proposal/approve|reject`) · `answer-question` · `inbox-sync` · `find-contacts` · `draft-outreach` · `learn-voice`

## Gotchas
- `.venv` inside an iCloud-synced folder gets the macOS hidden flag and "* 2.py" duplicates; keep the
  checkout outside iCloud. If `import careeros` breaks: `chflags -R nohidden .venv` or `PYTHONPATH=src`.
- In a worktree the shared `.venv` imports another checkout's `src/`: prefix pytest and openapi regen with `PYTHONPATH=src`.
- Tracker default `data/JobTracker.xlsx` (override `config/pipeline.yaml: paths.tracker_xlsx`). Always write via
  `careeros.tracker.Tracker` or the `careeros` CLI (atomic). If Excel has it open, ops queue to `.pending.json`; `careeros tracker flush`.
- `data/` is gitignored; regenerable via scout.
- `profile/voice/samples/` empty until the candidate adds samples → cover letters flagged `voice_verified: false`.

## Testing (TDD) — required for every code PR
- Red → green → refactor. Write the failing test first, commit it with the fix/feature in the same PR.
- Every code PR ships **unit tests** (`@pytest.mark.unit`, pure functions/classes, fakes for IO) **and
  integration tests** where the change crosses a boundary (`@pytest.mark.integration`, `tests/integration/`):
  CLI via subprocess on a temp repo root, scout → store → tracker with recorded HTTP fixtures,
  render.py → real PDF, qa over a full job dir, applier matching against the `examples/profile/` files.
- Tests read only the repo (`examples/`, `tests/fixtures/`) and tmp; never `profile/`, `config/`, `data/` or `$HOME`
  (CI has none of them).
- No network in tests (recorded fixtures only). LaTeX-dependent tests `skipif` no engine.
- Bug fix = a test that reproduces the bug first.
- Skill-only (SKILL.md) or docs-only PRs are exempt, but any Python a skill calls is not.
- `.venv/bin/python -m pytest -q` (all), `-m unit`, `-m integration`. CI runs both on every PR.
- Runs in parallel (`-n auto` in addopts); one test or a debugger: `.venv/bin/python -m pytest -n0 tests/x.py::t`.
- While coding: run only touched tests (path / `-k`).
- Before pushing a code PR: full `pytest -q` locally, then `gh pr merge --auto --squash`. CI full suite is the gate.
- Before merging a private sync PR: full `pytest -q` locally.
- Docs/skill-only changes: no tests.
- CI splits PR runs into shards (`CAREEROS_TEST_SHARD`/`CAREEROS_TEST_SHARDS`, hash of node ID, `tests/conftest.py`);
  the required `pytest` check aggregates them. Reproduce one shard locally with the same env vars.

## Git / PR workflow
- Never push to `main`. One branch per change (`feat/…`, `fix/…`, `docs/…`), open a PR with `gh pr create`.
- Stacked PRs are fine: set `--base` to the parent branch. GitHub retargets children when the parent merges.
- Review with `/review <PR>` (Claude + Codex in parallel, merged findings). `--post` comments on the PR.
- Merge only after `/review` returns `None.` or remaining findings are consciously accepted.
- `--admin` can't skip protection: wait for `pytest`, then `gh pr merge --squash` (or `--auto`).
- UI bundle conflicts: never hand-merge `src/careeros/ui/static/`; `git checkout origin/main -- src/careeros/ui/static`,
  rebuild, update UI snapshots. Merge UI PRs one at a time.

## Response format
Every reply that finishes a piece of work ends with a `**Next:**` block: numbered, concrete next steps split into
"you" (inputs/decisions the candidate owes) and "me" (what I'll do on go-ahead). Keep it to the top 3–5 items.

## Learning
Evidence lives in `.agent/LESSONS.md`, stable design decisions in `.agent/DECISIONS.md`; search them when relevant,
don't load whole. Record/promote per `~/.agent-learning/PROTOCOL.md` (or the `learn` skill). Promoted rules go in
this file; AGENTS.md points here.

## Product system
This repo uses `/product` (docs + how-to: `docs/product/README.md`). Any agent, any task touching product behaviour:
- Read `docs/product/STATUS.md` first. Scope reads via `~/.claude/skills/product/scripts/trace.py ids <ID>`; don't load all docs.
- Bug → Fix lane (failing test first). Feature → `/product new`. Never change REQ/SCOPE/acceptance silently: `/product change <ID>`.
- Any UI work: apply `~/.claude/skills/product/UI_UX_PRINCIPLES.md` (global UX heuristics, P1–P20, verification checklist).
- Missing requirement / UX / design detail → add to `docs/product/OPEN_QUESTIONS.md` and ask; don't invent.
- PR body: `Implements: REQ-… UC-…` / `Verification: E2E-…`. Status `verified` only via `/product verify`.

## Work docs
Workstreams: `docs/work/<slug>/README.md` (Brief + Status) + `handoffs/YYYY-MM-DD-NN.md` (versioned, never deleted).
Fresh agent: read only your stream's README + newest handoff. Global map of all work: `~/Code/WORK.md` (`/docs`).
Requirements stay in `docs/product/` (link IDs, don't copy). Branch name `work/<slug>` ties a branch to its stream.
