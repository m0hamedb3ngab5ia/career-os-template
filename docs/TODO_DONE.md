# TODO: completed items (archive, cold)

Verbatim from `TODO.md` before the audit. Not read at session start. Open work lives in `TODO.md`.

## System — build backlog
- [x] P0 config + profile schema, `examples/` candidate, `careeros init` (copy / `--link`)
- [x] P1 scout (greenhouse/lever/ashby) + tracker xlsx + CLI (`tracker applied-count`, `tracker upsert`)
- [x] P2 score-job, tailor-resume, write-cover-letter, answer-question, qa-review skills
- [x] P2.5 QA `confidential_terms` hard check (`profile/confidential_terms.yaml`)
- [x] Outreach relationship gate: connected (1st degree) or mutuals → never automated, `send_linkedin` "tailor manually" (`careeros outreach check|mark`, `pipeline.yaml: outreach`)
- [x] Unattended runs: `careeros run score|prepare` (ranking with "why", budget presets, one headless skill call per
      job, stop reasons, run history in `data/runs/`), global + per-job locks (`careeros job lock`), retry once then
      an Action Item, daily apply cap in code (`careeros run cap`), `runs.auto_submit` as config only
- [x] Scheduler: `careeros tick` + macOS LaunchAgent (`careeros schedule install`), quiet hours, pause/resume,
      one pending catch-up for missed slots, weekly prune, run-log retention
- [x] `careeros storage` (bytes by category, snapshots) + `careeros advise` / `advise apply <id>` (suggest-only)
- [x] SQLite run index (`data/careeros.db` `runs` table) for the UI, rebuilt from `data/runs/` (`docs/UI.md`)
- [x] `careeros ui` server: index (jobs, status history, action items, contacts, runs), file watcher + SSE,
      `/api/health|meta|status|jobs|events`, `pipeline.yaml: ui` (slice 1 of the UI build; frontend next)
- [x] `careeros doctor`: validate the candidate's own config/profile against the example schema, fail on
      untouched example data; `docs/GETTING_STARTED.md`

## Future (not now)
- [x] Web UI dashboard (jobs pipeline, action items, contacts, stats); built as `careeros ui` (PRs #34–#59). Design spec: `docs/UI.md`. Action Items section: every item shows its `Link` as a clickable hyperlink (e.g. "review & submit" opens the prepared application form) — reads tracker/data; likely local FastAPI + simple frontend, or Artifact page fed from tracker.

## Ghost jobs
- [x] Old (30 info / 45 review), skip only when old + not updated + company not posting + not evergreen/senior;
      reposted (3+ requisitions in 90 days, edits counted separately); aggregator-only; freeze covering the role
      (review) / layoffs (info). `src/careeros/safety/ghost.py`, `data/posting_history.json`, `careeros safety signal`.

## Safety — scam / data-harvesting protection
- [x] Safety verdicts Pass / Review / Block with reason codes + evidence (`careeros safety check|fields`, `src/careeros/safety/scam.py`); per-code levels in `targets.yaml: safety.levels`. Unknown companies = review, not suspicious; `careeros safety verify --risk low|medium|high` from independent signals. Registry entries carry confidence, evidence, expiry and `careeros safety clear`. Made-up companies: anything off the curated lists is `company_unverified` (no auto-submit) until /score-job verifies it (`careeros safety verify`); brand look-alikes on foreign domains are a hard stop. Hard stops (→ Action Item, never auto):
      any field asking SSN / DOB / bank / passport / driver's license / ID upload / mother's maiden name; pay-to-apply or "training fee";
      apply URL domain ≠ company domain and ≠ known ATS (greenhouse/lever/ashby/workday/icims/smartrecruiters/…); contact email on free domain (gmail/outlook/yahoo);
      company has no resolvable website / LinkedIn page / < N employees; posting text hits scam patterns (WhatsApp/Telegram interview, "hiring immediately, no interview", crypto wallet, check-cashing, "equipment reimbursement");
      salary wildly above market for level. Soft flags lower fit score and require review.
- [x] Allowlist (`auto_submit_allowed`, `safety.json`): auto-submit only on the ATS families in `targets.yaml: safety.auto_submit_ats` reached from a company-owned domain or the company's ATS board (scout-sourced). Postings from aggregators (Jobright/Handshake/LinkedIn) must resolve to that before auto.
- [x] Data minimization (`answer_for`: optional street blank; `sensitive` labels never answered): applier never enters anything not in `standard_answers.yaml`; address = city/state/zip only unless required by a verified ATS; phone/email are the only PII given by default.
- [x] `detection.yaml`-style registry for flagged companies/domains (`data/flagged_registry.yaml`, `careeros safety flag`), consulted by scout to drop future postings.
