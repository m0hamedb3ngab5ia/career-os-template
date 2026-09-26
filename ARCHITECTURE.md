# career-os — Architecture

Job-search automation for one candidate. One repo, config-driven, shareable: the code and a fictional
example candidate (`examples/`) are committed; the real candidate's `profile/` and `config/` are not.

## Principles

1. **Master profile is the only source of truth.** Every résumé bullet, cover-letter claim, and form answer must trace to `profile/master.yaml`. Fabrication = hard fail.
2. **Configurable, not hardcoded.** Categories, tiers, keywords, salary floors, blocked countries, templates, autonomy levels live in `config/*.yaml`. Personal facts live in `profile/`.
3. **Uncertain → Action Items, never guess.** Anything the system can't do confidently lands in the `Action Items` tab of the tracker for the candidate.
4. **Self-review.** Every generated artifact goes through `qa` before use. QA results are logged per job.
5. **Subscription first, API never (unless confirmed).** All LLM work runs through Claude Code (`claude -p` headless + skills in `.claude/skills/`). No Anthropic API key in this repo.
6. **One application per company per role family.** Dedup by company + normalized title; cooldown window per company.
7. **Personal data stays private.** `profile/`, `config/`, `CLAUDE.local.md`, `data/` are gitignored. `careeros init`
   creates them from `examples/` or symlinks them from the candidate's own private repo (`--link`).
   `profile/confidential_terms.yaml` lists the current employer's internal names; QA hard-fails any artifact containing one.

## Components

| # | Component | Location | Runs | Status |
|---|-----------|----------|------|--------|
| 0 | Setup | `careeros init` (`src/careeros/bootstrap.py`), `examples/` | once | copy or `--link` |
| 1 | Master profile | `profile/master.yaml`, `profile/standard_answers.yaml`, `profile/confidential_terms.yaml`, `profile/voice/` | — | candidate-owned |
| 2 | Scout | `src/careeros/scout/` | daily | Greenhouse/Lever/Ashby APIs |
| 3 | Scorer / categorizer | `.claude/skills/score-job/` | per job | Claude skill |
| 4 | Tailor (résumé) | `.claude/skills/tailor-resume/` + `templates/resume/` | per job ≥ threshold | LaTeX |
| 5 | Writer (cover letter + app questions) | `.claude/skills/write-cover-letter/`, `.claude/skills/answer-question/` | per job | voice from `profile/voice/` |
| 6 | QA gate | `.claude/skills/qa-review/` + `src/careeros/qa.py` | before every submit | truth/keyword/ATS/banned/confidential/specificity |
| 7 | Applier | `src/careeros/apply/` + Chrome (Claude in Chrome) | apply session | one adapter per ATS |
| 8 | Tracker | `src/careeros/tracker.py` → `data/JobTracker.xlsx` (configurable) | always | tabs: Jobs, Action Items, Contacts, Log, Config |
| 9 | Inbox sync | `.claude/skills/inbox-sync/` (Gmail MCP) | daily | status updates + push on interview |
| 10 | Outreach | `.claude/skills/find-contacts/`, `.claude/skills/draft-outreach/` | after apply | draft-only LinkedIn; Gmail auto-send after template confirmed |

## Data flow

```
scout ──► data/jobs/<job_id>/posting.json
            │
            ▼
        score-job ──► score.json  (category, tier, fit, hard_filter_fails, reasons)
            │ fit >= threshold && no hard fail && not blocklisted
            ▼
      tailor-resume ──► resume.tex/.pdf/.txt
  write-cover-letter ──► cover_letter.md/.pdf
     answer-question ──► answers.json  (per form question)
            │
            ▼
        qa-review ──► qa.json   pass → queue; fail → regenerate once → Action Items
            │
            ▼
         applier  ──► submits (if tier allows auto) OR Action Item with screenshot
            │         └► submitted/<stamp>/  frozen copy of what went out + form values (manifest.json)
            │
            ▼
         tracker  ──► JobTracker.xlsx row updated (careeros tracker upsert), Log appended
            │
            ▼
      inbox-sync  ──► status changes, interview → push notification + Action Item
            │
        outreach  ──► Contacts tab: name, LinkedIn URL, email (if found), draft msg
```

## Job lifecycle (tracker `Status` column)

`found → scored → skipped | queued → prepared → needs_review → applied → screening → interview → offer | rejected | withdrawn | ghosted`

## Autonomy tiers (`config/targets.yaml`)

- **A** — dream firms. Full prep, **never auto-submit**. Outreach prioritized.
- **B** — strong fit. Auto-submit on supported ATS after QA pass. Review only failures.
- **C** — volume. Auto-submit, no cover letter unless required.

Per-job override possible via tracker `Override` column.

## Where the LLM runs

Skills in `.claude/skills/` are invoked two ways:
- Interactively: `/score-job data/jobs/<id>` inside Claude Code.
- Headless from pipeline: `claude -p "/score-job data/jobs/<id>" --output-format json` (subscription-billed, no API key).

## Directories

```
career-os/
  ARCHITECTURE.md  README.md  TODO.md  CLAUDE.md  (CLAUDE.local.md: gitignored, personal)
  examples/  config/ + profile/ for the fictional candidate "Alex Example" (copied by `careeros init`)
  config/    targets.yaml  categories.yaml  companies.yaml  qa.yaml  pipeline.yaml        (gitignored)
  profile/   master.yaml  standard_answers.yaml  confidential_terms.yaml  voice/        (gitignored)
  templates/ resume/ (LaTeX)  cover_letter/  outreach/  followup_email/
  src/careeros/  bootstrap.py  scout/  apply/  tracker.py  qa.py  store.py  cli.py
  .claude/skills/  score-job  tailor-resume  write-cover-letter  answer-question  qa-review  inbox-sync  find-contacts  draft-outreach  apply-job  prepare-job  learn-voice
  data/      jobs/<job_id>/  seen.json  JobTracker.xlsx                                  (gitignored)
```
