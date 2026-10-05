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
- `.venv/bin/careeros learn answer "<question>" "<answer>" [--job <id>] [--key k] [--match re ...] [--company X] [--eeo]`, `learn lesson "<text>" [--ats workday|greenhouse|lever|ashby|custom] [--company X] [--job <id>] [--tag t]`, `learn list [--ats] [--company] [--json]` — answers land in `profile/standard_answers.yaml`, hurdles in `profile/apply_lessons.yaml`; `action done <id> --answer "<text>"` learns a question/salary item's answer, then closes it
- `.venv/bin/careeros tracker applied-count [<company>] [--days N]`, `tracker upsert <job_id> --field Header=value ...`, `tracker sync|flush|init`
- `.venv/bin/careeros run score|prepare [--preset small|medium|large|max|custom] [--max-jobs N] [--max-minutes M] [--dry-run] [--json]` — budgeted batches, one headless skill call per job, never applies; `--job <id> [--force]` runs one job (exit 2 with the reason if it is not a candidate)
- `.venv/bin/careeros apply plan <job_id> [--json] [--schema-json PATH] [--lock-token T|--force]` — Greenhouse question schema -> `data/jobs/<id>/fill_plan.json` (legal/salary/EEO unanswered pause, sensitive = exit 3); `apply fill <job_id> [--cdp http://localhost:9222] [--url U] [--lock-token T|--force]` — stages the plan in the browser via Playwright (`pip install -e '.[fast-apply]'`), reads every value back -> `fill_summary.json` + 1 screenshot; refuses blocked/unanswered plans; never submits. The filled tab stays open in a detached browser (CDP `paths.apply_cdp`, default 127.0.0.1:9223; `application.json` records it); UI `GET/POST /api/jobs/{id}/application[/open]` = liveness / focus-or-refill
- `.venv/bin/careeros creds set <site> [--username U] [--notes N] [--password-stdin|--no-password]`, `creds get <site> [--json|--reveal]`, `creds list [--json]` (no secrets), `creds rm <site>` — ATS/job-site logins for `/apply-job` in `paths.credentials` (default `~/.careeros/credentials.yaml`, 0600, outside git; `credentials.backend: file|keychain`); run logs mask stored passwords
- `.venv/bin/careeros resume feedback <rid>`, `resume review-save <rid> <items.json>`, `resume apply-edit <rid> <item> <base> <text>` (zero-fabrication guard; exit 1 = refused or `<base>` not the latest), `resume redraft <rid> <item> "<suggestion>"` (hand edit = UI only, PUT .../text) — review/edit lifecycle (REQ-094..097) used by `review-resume` / `edit-resume`; run kinds `review`, `resume_edit`; a new master version launches `extract_master`
- `.venv/bin/careeros run apply --job <id> [--json]` — `/apply-job` one prepared job headless (Chrome MCP tools allowed); `--job` required, Tier A staged for review, never submitted, never scheduled
- `.venv/bin/careeros batch create <job_id>... --stop-at score|prepare|fill|submit [--name N] [--dry-run] [--json]`, `batch show <id> [--json]` — plan a batch (`data/runs/batches/<id>.json`): per-job first stage + exclusion reasons; LinkedIn excluded from fill/submit, Tier A never auto-submitted, one job per run; `batch run <id>` (driver: one job at a time, one run per stage, re-checks LinkedIn + auto-submit before each apply; exit 6 = running), `batch pause|cancel <id>`, `batch retry <id> [--job J]`; API `POST /api/batches`, `GET /api/batches/{id}`, `POST /api/batches/{id}/start|pause|cancel|retry`
- `.venv/bin/careeros resume match <job_id> [--threshold N] [--json]` — deterministic match score 0-100 of every résumé (latest version) vs the job, best first, missing skills (DEC-003; `targets.yaml: thresholds.min_match`, `pipeline.yaml: match.synonyms`); API `GET /api/jobs/{id}/matches[?threshold=N]`
- `.venv/bin/careeros run list|show <id> [--json|--log]|status|cap [--check]|pause [--until +2h|ISO] [--reason]|resume|catch-up [--dry-run|--dismiss]`
- `.venv/bin/careeros job select|unselect <id>...` (REQ-104: new postings start unticked; prepare/apply runs, batches and tick take only ticked jobs; `run --job X` ticks X; API `POST /api/jobs/select`)
- `.venv/bin/careeros job lock|unlock|check <id>` (exit 6 = held), `tick [--dry-run]`, `schedule install|uninstall|status` (LaunchAgent → `careeros tick`)
- `.venv/bin/careeros ui [--port 8765] [--reindex] [--no-open]` — local web app on 127.0.0.1 (needs `pip install -e ".[ui]"` + `playwright install chromium` for Fill application); SQLite index `data/careeros.db` is disposable
- `.venv/bin/careeros resume list [--json]`, `resume add <file.pdf|docx> [--name N] [--type master|variant|other|tailored] [--json]` — résumé store `profile/resumes/<rid>/` (meta.json + v<n>/original, text.txt, ats.json); first résumé = master; API `PUT /api/profile/resumes?filename=` (raw body, ≤5 MB), `GET/PATCH/DELETE /api/profile/resumes/{rid}[/versions/{n}]`, `POST .../{rid}/master` (409 = master/latest-version rule)
- `.venv/bin/careeros prune [--yes]`, `storage [--json] [--snapshot]`, `advise [--json]`, `advise apply <id>` (suggest-only; writes config/pipeline.yaml only on apply)
- `.venv/bin/careeros sync status [--remote template] [--no-fetch] [--json]|pull [--branch B] [--no-checks]|install-hook [--force]` — private copy vs the public template (status exit 0 in sync, 1 behind, 2 drift; pull exit 3 = conflicts; `.template-sync-keep` lists intentional differences)
- `.venv/bin/python -m careeros.qa data/jobs/<id>` — deterministic QA
- `.venv/bin/python templates/resume/render.py data/jobs/<id>/resume.json` — tex+pdf+txt
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
