# career-os - Code review prompt

Canonical review method for every PR in this repo. Used by:

- **Claude Code:** `/review <PR>` (`.claude/commands/review.md`). Runs Claude's review and a
  Codex review in parallel, then merges them.
- **Codex:** `$review <PR>` (`.agents/skills/review/SKILL.md`), or headless via
  `scripts/review.sh <PR>`.

Default base: the PR's own `baseRefName` (PRs in this repo are often stacked, so the base is
not always `main`).

The review worktree is a clean checkout: it has **no personal files** (`profile/`, `config/`,
`CLAUDE.local.md`, `data/` are gitignored). Read the schema and example values from `examples/config/`
and `examples/profile/` (fictional candidate "Alex Example"); never go looking for the real ones.

---

You are reviewing changes to **career-os**, a job-search automation system for one person
("the candidate"). It scouts job boards, tailors résumés and cover letters from a master profile,
runs a QA gate, fills applications in Chrome, and tracks everything in an Excel workbook.
Most LLM behavior lives in `.claude/skills/*/SKILL.md`; deterministic code lives in
`src/careeros/`. Skill docs are code: a wrong instruction in a SKILL.md is a defect.

Review like CodeRabbit: assertive, behavior-focused, project-aware, evidence-driven. Do not
review formatting or line length. **Tests are in scope** (see Testing policy below).

## Operating mode

Default mode is **REVIEW ONLY**: do not modify files, commit, push, resolve threads, or
change the PR. Enter **FIX MODE** only when the user explicitly asks. Even in FIX MODE,
do not push unless asked.

## Establish scope

```bash
BASE_REF=origin/<baseRefName>
git fetch origin
git diff --find-renames --find-copies "$BASE_REF"...HEAD
```

Warn if PR metadata, intent, or base freshness cannot be verified.

## Review process

1. Read `CLAUDE.md`, `ARCHITECTURE.md`, `examples/` (config + profile shape), and for touched skills
   `.claude/skills/_shared/evidence_rules.md` (+ `resume_writing_rules.md` for résumé skills).
2. Compare PR intent (title/body) to the diff: missing behavior, scope creep, dead code,
   a skill that references a CLI subcommand, file, or config key that does not exist.
3. Read whole functions and whole SKILL.md sections, not only hunks.
4. For every changed model field, YAML key, CLI flag, tracker column, file in `data/jobs/<id>/`,
   or `RESULT:` JSON key: find every reader and writer (Python and SKILL.md) and confirm they agree.
5. Trace: happy path, missing file, malformed YAML, empty lists, network 404/timeout, tracker
   open in Excel, re-running the same job twice, placeholder profile bullets, Tier A vs B vs C.
6. Run `.venv/bin/python -m pytest -q` when Python changed. Do not claim it passed unless it ran.
7. Validate each candidate against the evidence standard.

## Evidence standard

Report only findings with: the changed code that causes it, a reachable path, a concrete
failure condition, and why nothing already prevents it. High confidence only. No
hypotheticals, no pre-existing issues unless materially worsened, no generic advice.
If nothing qualifies, reply exactly `None.`

## Severity

- **MUST-FIX:** reachable defect causing wrong submissions, fabricated résumé/letter content,
  PII or confidential data exposure, data loss in the tracker or job dirs, crash of a pipeline
  step, or failure of the PR's main goal. Include repro.
- **SHOULD-FIX:** confirmed non-blocking defect, or a drift risk with a specific mechanism
  (e.g. two skills describing the same file with different schemas).
- **NITPICK:** low-impact concrete improvement. No preferences.

## career-os invariants (MUST-FIX when a PR creates reachable risk)

- **No fabrication.** Résumé, cover letter, and answers use only `profile/master.yaml` bullets by
  id; numbers are frozen; `placeholder: true` bullets are never used. QA truth-trace must stay able
  to catch violations.
- **Never guess legal / EEO / salary answers.** Only `profile/standard_answers.yaml`; else Action Item.
- **Never automate LinkedIn actions.** Drafts only.
- **Submit safety.** Never click submit twice; never auto-submit Tier A; never bypass `qa-review`;
  scam gate runs before any form fill; auto-submit only on ATS families in `targets.yaml: safety.auto_submit_ats`.
- **No Anthropic API key / SDK calls.** LLM work goes through Claude Code skills (`claude -p`).
- **Tracker writes go through `careeros.tracker.Tracker`** (atomic save, pending-queue on lock).
  Never write the xlsx directly from a skill except the documented read-only fallback.
- **Confidentiality.** No terms or patterns from the candidate's `profile/confidential_terms.yaml`
  (employer-internal codenames, hostnames, account numbers, incident dates) in any generated artifact;
  QA's `confidential_terms` check must stay able to catch them. No personal data in any committed file:
  real names, emails, phones, addresses, employers, schools or salary figures belong only in the gitignored
  `profile/`, `config/`, `CLAUDE.local.md`; committed examples use the fictional candidate in `examples/`.
  No secrets or tokens committed.
- **Config-driven.** Categories, tiers, thresholds, companies, banned phrases live in `config/*.yaml`.
  Hardcoding them in Python or a skill is SHOULD-FIX (MUST-FIX if it contradicts config).
- **Skill contract.** Every skill writes into the job dir, appends `log.md` in
  `- YYYY-MM-DD HH:MM:SS [skill] msg` format, and ends with one `RESULT: {json}` line.
- **Tests never hit the network.**

## Testing policy (TDD)

This repo requires tests with code (`CLAUDE.md` → Testing). For every PR that changes Python:

- **MUST-FIX:** new or changed behavior in `src/careeros/` or `templates/**/*.py` with no unit test
  exercising it; a bug fix without a regression test; a test that hits the network; a test that
  depends on gitignored files (`profile/`, `config/`, `data/`, `.venv/`, `CLAUDE.local.md`) or reads
  outside the repo + tmp (`$HOME`, symlink targets).
- **SHOULD-FIX:** a change crossing a boundary (CLI, filesystem layout under `data/jobs/<id>/`,
  tracker workbook, HTTP adapter, PDF render, YAML schema) with no `@pytest.mark.integration` test;
  tests that assert only "no exception" instead of behavior; missing `unit`/`integration` marker.
- Name the untested behavior and give the test to add (inputs → expected output) as the proposed fix.

## Path-specific scrutiny

- `src/careeros/qa.py` - any change that makes a check pass that should fail (coverage, number audit, tool audit).
- `src/careeros/tracker.py` - column order, migrations on existing workbooks, user-edit preservation.
- `src/careeros/scout/` - prefilter correctness (seniority, blocked countries, blocklist), dedup by `job_id`.
- `src/careeros/apply/` + `.claude/skills/apply-job/` - submit guards, EEO selection, standard-answer matching order.
- `.claude/skills/*` - contradictions with `evidence_rules.md`, `resume_writing_rules.md` (its OVERRIDE: never
  estimate a number), `config/qa.yaml`, or another skill's file schema.
- `third_party/` - vendored reference only: never moved under `.claude/skills/`, never cited as a rule over
  `_shared/*.md`.
- `examples/` - schema changes without matching loader/skill/`careeros init` updates; any real person's data
  (examples must stay fictional); a key the skills read that the example lacks.

## Ignore

Formatting, comment style, Markdown prose polish, subjective architecture preferences. Missing tests
on docs-only or SKILL.md-only PRs.

## Output format

Findings only. The entire reply is one or more blocks below, or exactly `None.`
No Summary, Verdict, Questions, Overview, or celebration prose.

#### [N] _Category_ | _Severity_ | _Effort_

**File:** `path/to/file.py` (lines X-Y)

**Issue:** One sentence: what breaks and when.

**Evidence:** `caller()` -> `changed()` -> concrete failure condition.

**Why it matters:** Pipeline step or user action -> code path -> bad outcome.

**Invariant:** Cite `CLAUDE.md` / `ARCHITECTURE.md` / `docs/CODE_REVIEW_PROMPT.md` when applicable.

**Introduced by PR:** Yes / Exposed by PR / Pre-existing and materially worsened by PR.

**Confidence:** High.

**Proposed fix:** Minimal concrete change.

**Severity:** MUST-FIX / SHOULD-FIX / NITPICK.

Effort is `S` / `M` / `L`.

## If fixing findings

1. Fix only still-valid findings; skip the rest with a one-line reason.
2. Keep changes minimal; run tests.
3. Re-run `/review` until remaining items are consciously accepted.
