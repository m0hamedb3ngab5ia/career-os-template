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
- `.venv/bin/careeros scout --sync` — pull boards, prefilter, store, sync tracker
- `.venv/bin/careeros jobs list [--status queued]`, `job show <id>`, `job status <id> <status> [--note]` (status.json + tracker), `stats`, `action list`, `action add "<what>" --type <t> --needs laptop|phone|anytime`
- `.venv/bin/careeros tracker applied-count [<company>] [--days N]`, `tracker upsert <job_id> --field Header=value ...`, `tracker sync|flush|init`
- `.venv/bin/careeros run score|prepare [--preset small|medium|large|max|custom] [--max-jobs N] [--max-minutes M] [--dry-run] [--json]` — budgeted batches, one headless skill call per job, never applies
- `.venv/bin/careeros run list|show <id> [--json|--log]|status|cap [--check]|pause [--until +2h|ISO] [--reason]|resume|catch-up [--dry-run|--dismiss]`
- `.venv/bin/careeros job lock|unlock|check <id>` (exit 6 = held), `tick [--dry-run]`, `schedule install|uninstall|status` (LaunchAgent → `careeros tick`)
- `.venv/bin/careeros prune [--yes]`, `storage [--json] [--snapshot]`, `advise [--json]`, `advise apply <id>` (suggest-only; writes config/pipeline.yaml only on apply)
- `.venv/bin/careeros sync status [--remote template] [--no-fetch] [--json]|pull [--branch B] [--no-checks]|install-hook [--force]` — private copy vs the public template (status exit 0 in sync, 1 behind, 2 drift; pull exit 3 = conflicts; `.template-sync-keep` lists intentional differences)
- `.venv/bin/python -m careeros.qa data/jobs/<id>` — deterministic QA
- `.venv/bin/python templates/resume/render.py data/jobs/<id>/resume.json` — tex+pdf+txt
- `.venv/bin/python -m pytest -q`

## Skills (`.claude/skills/`)
`prepare-job` (orchestrates score-job → tailor-resume → write-cover-letter → qa-review) · `apply-job` (Chrome) · `answer-question` · `inbox-sync` · `find-contacts` · `draft-outreach` · `learn-voice`

## Gotchas
- `.venv` inside an iCloud-synced folder gets the macOS hidden flag and "* 2.py" duplicates; keep the
  checkout outside iCloud. If `import careeros` breaks: `chflags -R nohidden .venv` or `PYTHONPATH=src`.
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

## Git / PR workflow
- Never push to `main`. One branch per change (`feat/…`, `fix/…`, `docs/…`), open a PR with `gh pr create`.
- Stacked PRs are fine: set `--base` to the parent branch. GitHub retargets children when the parent merges.
- Review with `/review <PR>` (Claude + Codex in parallel, merged findings). `--post` comments on the PR.
- Merge only after `/review` returns `None.` or remaining findings are consciously accepted.

## Response format
Every reply that finishes a piece of work ends with a `**Next:**` block: numbered, concrete next steps split into
"you" (inputs/decisions the candidate owes) and "me" (what I'll do on go-ahead). Keep it to the top 3–5 items.
