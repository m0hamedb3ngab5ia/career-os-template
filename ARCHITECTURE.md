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
| 6 | QA gate | `.claude/skills/qa-review/` + `src/careeros/qa.py` + `qa_ext/` | before every submit | truth/keyword/ATS/banned/confidential/specificity |
| 7 | Applier | `src/careeros/apply/` + Chrome (Claude in Chrome) | apply session | one adapter per ATS |
| 8 | Tracker | `src/careeros/tracker.py` → `data/JobTracker.xlsx` (configurable) | always | tabs: Jobs, Action Items, Contacts, Log, Config |
| 9 | Inbox sync | `.claude/skills/inbox-sync/` (Gmail MCP) | daily | status updates + push on interview |
| 10 | Outreach | `.claude/skills/find-contacts/`, `.claude/skills/draft-outreach/` | after apply | draft-only LinkedIn; Gmail auto-send after template confirmed; connected / mutuals → tailored by hand (`careeros outreach`) |
| 11 | Runner | `src/careeros/runs/` (`careeros run score\|prepare`) → `data/runs/` | on demand or scheduled | Python ranks and budgets; one headless skill call per job; never applies |
| 12 | Scheduler | `careeros tick` (`runs/tick.py`, `runs/schedule.py`) + macOS LaunchAgent (`careeros schedule install`) | every 15 min | scout, score, prepare, prune when due; quiet hours; catch-up |
| 13 | Storage + advisor | `careeros storage`, `careeros advise [apply <id>]` | after each prune / on demand | suggest-only; a config change only on `advise apply` |

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

Unattended, the first half runs in batches (see "Runs and scheduling"): `careeros tick` → scout →
`careeros run score` (score-job per job) → `careeros run prepare` (prepare-job per job) → jobs end `queued` or
`needs_review`. Applying stays a separate, attended step.

## Applications per company (`src/careeros/company_policy.py`)

Pure functions over job records (status.json, score.json, tracker DateApplied, posting close date):
`slots` (submitted in the cap window + reservations whose posting has not closed), `rank_candidates`
(candidates = scored `prepare` or gate-deferred `company_cap` / `cooldown`, read from score.json or the
`skipped` status note; other skips, and postings `careeros prune` stubbed, never compete; similar roles by fit; during a
rejection cooldown, roles that close before it ends first), `gate` (allowed, reason, urgent, closes_at),
`transparency_note`. Close dates: Greenhouse `application_deadline` or a custom metadata field, else the
description text ("apply by", "applications close", "deadline", "closing date", "no later than" + a
date); Lever and Ashby have no deadline field, text only. Unknown = None, and the cooldown applies.
Scout stores it as `closes_at` in posting.json. CLI: `careeros company slots|gate|active|requeue`;
score-job and prepare-job gate before tailoring, apply-job before submitting.

## QA gate checks

`python -m careeros.qa <job_dir>` (`src/careeros/qa.py`) runs every deterministic check and prints one JSON report;
`pass` is false when any hard check fails. The core checks (truth trace, bullet fidelity, number/tool audits,
banned phrases, confidential terms, contact, page count, keyword coverage) live in `qa.py`. The extended checks live
in `src/careeros/qa_ext/` and read the Checker's shared inputs (`pipeline_cfg`, `companies_cfg`, `jobs_dir`,
`outreach`, `contacts`); each writes its findings to an extra report key:

| module | hard checks | soft checks | report key |
|---|---|---|---|
| `company.py` | `wrong_company`: a known company (companies.yaml, other job dirs) that is not this job's, in the letter, a generated answer or an outreach draft | — | `wrong_company_hits` |
| `consistency.py` | `employer_title_consistent` (title/degree/year vs the résumé header), `numbers_consistent` (a restated bullet number) | `letter_experiences_on_resume`, `employer_title_uncertain`, `numbers_paraphrased` | `consistency` |
| `outreach_policy.py` | `outreach_manual_contacts`, `linkedin_draft_only`, `linkedin_note_length` (> 300 chars), `email_autosend_verified`, `thank_you_manual`, `outreach_cold_limit`, `outreach_json_valid` | `outreach_word_counts` | `outreach_policy` |
| `pdf_fidelity.py` | `pdf_links_clickable`, `pdf_text_matches_resume` | `pdf_text_split_words`, `pdf_hidden_text`, `pdf_fonts_embedded`, `pdf_metadata` | `pdf_fidelity` |

**Bold markup.** Bullet `text` / `variants` and `summary_variants` in `profile/master.yaml` may carry `**bold**`
spans (tech names, metrics). `src/careeros/markup.py` (`strip_bold`, `bold_spans`, `validate_bold`) is the one
parser: `templates/resume/render.py` turns each span into `\textbf{}` (escaping inside it) and writes resume.txt
plain; every truth / number / tool / keyword / consistency check compares stripped text, so markers never change a
verdict. `bold_markup` (hard) rejects invalid markup and `**` outside bullet text / summary in resume.json, and any
`**` in resume.txt; `no_markdown_bold` (hard) rejects `**` in answers and outreach and a stray `**` in the cover
letter; balanced bold in a letter is only the soft `cover_letter_bold`. `careeros doctor` FAILs on invalid markup
in master.yaml.

`cover_letter_names_company` (hard, in `qa.py`) accepts the company's configured aliases and domain stems. Every
threshold is optional config in `config/qa.yaml` (`consistency:`, `outreach:`, `pdf:`; defaults commented in
`examples/config/qa.yaml`). A job without `outreach.json` or `resume.pdf` skips those checks. `/qa-review` caps
`ats_safety` on the PDF checks and routes each failure to the writer skill that fixes it.

## Job lifecycle (tracker `Status` column)

`found → scored → skipped | queued → prepared → needs_review → applied → screening → interview → offer | rejected | withdrawn | ghosted`

## Autonomy tiers (`config/targets.yaml`)

- **A** — dream firms. Full prep, **never auto-submit**. Outreach prioritized.
- **B** — strong fit. Auto-submit on supported ATS after QA pass. Review only failures.
- **C** — volume. Auto-submit, no cover letter unless required.

Per-job override possible via tracker `Override` column.

## Where the LLM runs

Skills in `.claude/skills/` are invoked two ways, both on the Claude Code subscription (no API key):
- Interactively: `/score-job data/jobs/<id>` inside Claude Code.
- Headless from `careeros run` (one call per job, built from `pipeline.yaml: llm`):

  ```
  claude -p --output-format stream-json --verbose --permission-mode dontAsk \
    --allowedTools <llm.allowed_tools, comma-joined> --session-id <uuid> "/score-job data/jobs/<id>"
  ```

  Why each flag: `-p` runs one prompt and exits. `stream-json` (which requires `--verbose`) prints one JSON event
  per line as it happens, so the runner sees MCP server status (`system/init`), API errors (`authentication_failed`,
  `rate_limit`), rejected rate-limit events and tool `permission_denials` as structured data instead of guessing
  from text, tees the raw stream to `attempts/NNN.stream.jsonl`, and reads the skill's `RESULT:` line from the final
  `result` event. `--output-format json` only prints at the end, so a hung call shows nothing. `dontAsk` denies any
  tool not in `--allowedTools` instead of waiting for a prompt nobody will answer. `--session-id` is recorded per
  attempt so a failed call can be reopened in Claude Code.

## Runs and scheduling (`src/careeros/runs/`)

Python decides what to work on and when to stop; the LLM only does one skill on one job per call.

| Module | Does |
|---|---|
| `config.py` | `pipeline.yaml: runs` + `llm`, validated (a malformed budget is a ConfigError: runs never guess) |
| `ranking.py` | pure ranking with a `why` per job: freshness (full weight under `fresh_hours`, linear to 0 at `stale_days`) + dream bonus + deadline bonus + fit × `fit_weight` (prepare only) + retry bonus. Prepare runs keep the company gate's fit-first order inside each company |
| `runner.py` | the loop: rank → write `queue-<kind>.json` (dry run stops here) → global runner lock → preflight (pause, `careeros doctor`) → per job: job lock, headless call, classify, record, release |
| `headless.py` | builds the command, streams events, validates the `RESULT:` line (job id, `decision` for score, `status` for prepare), classifies the outcome |
| `service.py` | `run_batch`, what the CLI and the scheduler call: retry-once + Action Item, company gate before each prepare, daily-cap stop |
| `policy.py` | daily apply cap in code, `runs.auto_submit` rules, retry and prepare config |
| `locks.py`, `failures.py`, `store.py` | lock files, per-job failure counts, run history files |
| `schedule.py`, `tick.py`, `launchd.py` | the tick planner, `careeros tick` / `careeros run catch-up`, the LaunchAgent plist |

**Flow.** `careeros run score|prepare [--preset small|medium|large|max|custom] [--max-jobs N] [--max-minutes M]
[--dry-run]`. Presets set jobs per run and wall-clock minutes (medium (Recommended): 25 score / 5 prepare jobs,
90 minutes); the run stops at whichever comes first, and before a job the average job time says would overrun.
Score runs take `found` jobs without a score; prepare runs take jobs whose score says `prepare` (or requeued gate
deferrals) and that have no passing `prepare.json`. Jobs a run does not reach keep their status: nothing is
bulk-skipped. After a valid score-job RESULT the runner records `scored` or `skipped` (note starting with the skip
reason) unless the skill already moved the job.

**Stop reasons** (`run.json: stop_reason`): `completed`, `budget_reached`, `time_budget`, `daily_cap`, `paused`,
`cancelled` (the run did its job; CLI exit 0) and `usage_limit`, `auth_required`, `permission_denied`, `timeout`,
`consecutive_failures`, `doctor_failed`, `error` (needs you; exit 1; `error` = the single inbox_sync call failed another
way, or a run crashed). The run's time budget also caps the job in flight: a job cut at the budget stops the run
as `time_budget`, not `timeout`, and does not count against the job. A run that finds another holding the runner lock
never starts (exit 5). `usage_limit`, `auth_required`, `permission_denied` and `cancelled` end the run at once
(the next job would hit the same wall); `timeout` does with `runs.stop_on_timeout` (true, Recommended); three job
failures in a row (Recommended) end it as `consecutive_failures`. A usage-limit reset time in the error text is
never parsed or trusted; the next scheduled slot simply tries again.

**Locks.** `data/runs/runner.lock`: one batch at a time. `data/runs/locks/<job_id>.lock`: one worker per job. Lock
files carry owner, pid, host and expiry, are created atomically, and a stale one (expired, dead pid on this host,
unreadable) is taken over under a short `flock`. prepare-job and apply-job take the job lock themselves
(`careeros job lock <id> --owner <skill>`, exit 6 when held); inside a run they re-enter the runner's lock through
`CAREEROS_LOCK_TOKEN`. `careeros job status` refuses a locked job without the token. `careeros job check <id>` reports it.

**Retry.** Only the job's own failures count (`skill_error`, `invalid_result`, `error`, `timeout`) in
`data/runs/failures.json`. With `runs.retry.max_attempts: 2` (Recommended) a failed job is retried once in a later
run (retry bonus in the ranking); then it becomes an Action Item (deduped) and runs leave it out. Its status never
changes. A usage limit, login problem, denied tool or cancel says nothing about the job and does not count. A
failure that leaves the job where no run can pick it up again (e.g. a passing `prepare.json` with the status never
recorded) becomes the Action Item at once.

**Company gate in prepare runs.** Checked before each call: `company_cap` / `cooldown` only pass the job over (it
competes again later); any other block (`closed`, `not_similar`, `already_applied`) records it `skipped` with a note
`company <reason>: <detail>`. When a company being prepared still has unscored `found` jobs, the run warns (output,
`run.log`, `run.json: warnings`) but does not block: fit-first slot ranking only sees scored jobs.

**Daily cap.** `policy.py` computes today's cap as `targets.yaml: volume.max_applications_per_day` × this month's
`season_multiplier`, counted from DateApplied. apply-job checks it with `careeros run cap --check` (exit 3 when
reached). Prepare runs stop with `daily_cap` once the jobs ready to submit fill what is left of today's cap
(`runs.prepare.stop_at_daily_cap`, true, Recommended): preparing more than can be sent today is wasted work.

**Auto-submit is config only.** `runs.auto_submit` (`enabled: false` (Recommended), `allow`, `manual`) is parsed and
validated, and `auto_submit_decision` is the pure rule a future apply path will call (Tier A and a non-pass safety
verdict are always manual, whatever the config says; `manual: [tier_a, fit_gte_85]` (Recommended) keeps your best
matches manual, and the fit threshold is yours to change). Runs never apply in this version.

**Scheduler.** `careeros schedule install` writes a LaunchAgent (`~/Library/LaunchAgents/<schedule.launchd_label>.plist`,
absolute paths, a PATH with the `claude` it found, logs to `data/runs/launchd.out.log` / `launchd.err.log`) that
runs `careeros tick` every `schedule.tick_minutes` (15, Recommended). It is a per-user agent, not a daemon: it runs
as the candidate, with their Claude Code login, and only while they are logged in. A tick is idempotent
(`data/runs/tick.lock`, never waits) and runs what `schedule.jobs` says is due, in order: scout (every 3 h),
inbox_sync (08:00 and 18:00, **off** until the inbox-sync skill is finished), score (nightly 01:00), prepare (nightly
02:00), prune (weekly), all Recommended. A job runs every N hours / days or at times of day (`at: ["HH:MM"]`, local);
a time-of-day job never fires on the first tick after install, only at its next slot. Quiet hours (09:00 to 18:00,
Recommended) hold back only the claude-using runs (inbox_sync, score, prepare). inbox_sync is one headless
`/inbox-sync` call (`service.run_skill`) whose `mcp_servers` (Gmail) must be logged in: a Gmail MCP reported
needs-auth, or the skill's `gmail_mcp_unavailable`, stops it with `auth_required` (it stops with `error` on any other
failure). Slots missed while the Mac slept or was off (more than
`missed_after_minutes` late; "asleep" = the gap since the previous tick ENDED, so a long run inside a tick never
counts) never auto-run: they collapse into one pending record (`data/runs/catch_up.json`, written under
`tick.lock`; `careeros run catch-up` holds the same lock and removes only the kinds it ran) that
the candidate starts with `careeros run catch-up` or drops with `--dismiss`. `careeros run pause [--until +2h|ISO]`
stops the current batch before its next job and makes ticks skip due slots (not stored up); `careeros run resume`
lifts it. State: `data/runs/schedule.json` (last tick, last run per job).

**History.** `data/runs/<run_id>/run.json` (kind, trigger, budget, counters, stop reason, timings),
`attempts/NNN.json` (job, stage, rank, why, session id, outcome, RESULT) + `NNN.stream.jsonl` (raw events),
`run.log`; `queue-<kind>.json` is the latest ranking. Files are canonical and written atomically; a SQLite index
for the UI is future work (`docs/UI.md`). `careeros run list|show|status` read them.

**Storage and advisor.** `careeros storage [--json] [--snapshot]` reports bytes by category (postings,
résumés/PDFs, screenshots, run logs, tracker, other) and disk free; a snapshot line is appended to
`data/runs/storage.jsonl` after every prune (`careeros prune --yes` and the scheduled weekly prune) and on
`--snapshot`. `careeros advise [--json]` is suggest-only. Storage advice starts once `advisor.advise_after_days`
(14, Recommended) of snapshots exist: projected 30 / 90-day growth against `storage.budget_mb` (1024, Recommended)
and `storage.warn_at_pct` (80, Recommended), disk free under `storage.disk_free_warn_pct` (10, Recommended), a prune
that removed nothing for `advisor.prune_idle_weeks` (4, Recommended) weeks (loosen retention), and the dominant
category (tighten that retention key). Run-efficiency advice starts once `advisor.min_runs` (5, Recommended) runs of
a kind exist in run.json history: time per job against the timeout, failure rate, scored → prepared %, budget
used and `usage_limit` stops, turned into preset or timeout suggestions. Each recommendation has an id and either
a concrete YAML change or advice only. `careeros advise apply <id>` applies that one change to
`config/pipeline.yaml` only when called: ruamel.yaml round trip (comments and order kept), validate, roll back
on failure. Nothing is ever applied automatically.

## Directories

```
career-os/
  ARCHITECTURE.md  README.md  TODO.md  CLAUDE.md  (CLAUDE.local.md: gitignored, personal)
  examples/  config/ + profile/ for the fictional candidate "Alex Example" (copied by `careeros init`)
  config/    targets.yaml  categories.yaml  companies.yaml  qa.yaml  pipeline.yaml        (gitignored)
  profile/   master.yaml  standard_answers.yaml  confidential_terms.yaml  voice/        (gitignored)
  templates/ resume/ (LaTeX)  cover_letter/  outreach/  followup_email/
  src/careeros/  bootstrap.py  scout/  apply/ (incl. snapshot.py)  safety/  tracker.py  qa.py  qa_ext/  store.py
                 company_policy.py  outreach.py  retention.py  doctor.py  cli.py
                 runs/ (config  ranking  runner  headless  service  policy  locks  failures  store  schedule  tick  launchd)
  .claude/skills/  score-job  tailor-resume  write-cover-letter  answer-question  qa-review  inbox-sync  find-contacts  draft-outreach  apply-job  prepare-job  learn-voice
  data/      jobs/<job_id>/  seen.json  JobTracker.xlsx                                  (gitignored)
             runs/  <run_id>/{run.json, run.log, attempts/NNN.json, NNN.stream.jsonl}  queue-<kind>.json
                    schedule.json  catch_up.json  pause.json  failures.json  storage.jsonl
                    runner.lock  tick.lock  locks/<job_id>.lock  launchd.out.log  launchd.err.log
```

## Retention (`careeros prune`)

`src/careeros/retention.py` plans, then (with `--yes`) applies two rules from `pipeline.yaml: retention`, both
measured from the job's last status change: closed jobs drop apply step screenshots after
`screenshots_after_closed_days` (confirmation shot kept), and never-prepared postings are rewritten as a stub
(`pruned: true`, description cut to a preview) after `unprepared_posting_days`. A stubbed found/scored job is set to
`skipped` (status.json and tracker, queued if the tracker is locked) so it leaves the prepare queue;
`careeros safety check`, score-job and prepare-job refuse a pruned posting. Files it changes:
`screenshots/`, `posting.json` and (for that status move) `status.json` inside `data/jobs/<id>/`; each change is logged in that job's `log.md`.

Run history has two more rules, measured from the run's end: after `run_logs_days` (30, Recommended) a run loses
`run.log` and its raw `attempts/*.stream.jsonl` (run.json and attempts/NNN.json stay for history and the advisor);
after `run_summaries_days` (365, Recommended) the whole `data/runs/<run_id>/` goes. A run still holding the runner
lock is never touched. The scheduler prunes weekly (`schedule.jobs.prune`), and every prune appends a storage
snapshot for `careeros advise`.
