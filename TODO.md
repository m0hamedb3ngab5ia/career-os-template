# TODO

Generic build backlog. Personal inputs (profile bullets, voice samples, dream list, board slugs)
belong in each candidate's own private repo, not here.

## System — build backlog
- [x] P0 config + profile schema, `examples/` candidate, `careeros init` (copy / `--link`)
- [x] P1 scout (greenhouse/lever/ashby) + tracker xlsx + CLI (`tracker applied-count`, `tracker upsert`)
- [x] P2 score-job, tailor-resume, write-cover-letter, answer-question, qa-review skills
- [x] P2.5 QA `confidential_terms` hard check (`profile/confidential_terms.yaml`)
- [ ] P3 applier: Chrome adapters greenhouse → lever → ashby; bot-detection heuristics; screenshot on every submit
- [ ] P4 inbox-sync (Gmail MCP) + push notify + follow-up drafts
- [ ] P5 find-contacts + draft-outreach (LinkedIn URL, email guess w/ verification, message)
- [x] Outreach relationship gate: connected (1st degree) or mutuals → never automated, `send_linkedin` "tailor manually" (`careeros outreach check|mark`, `pipeline.yaml: outreach`)
- [ ] P6 custom scrapers for `ats: custom` boards (company career pages without a public ATS API)
- [ ] P7 LinkedIn Jobs discovery (never Easy Apply)
- [ ] Workday adapter (assisted mode)
- [x] Unattended runs: `careeros run score|prepare` (ranking with "why", budget presets, one headless skill call per
      job, stop reasons, run history in `data/runs/`), global + per-job locks (`careeros job lock`), retry once then
      an Action Item, daily apply cap in code (`careeros run cap`), `runs.auto_submit` as config only
- [x] Scheduler: `careeros tick` + macOS LaunchAgent (`careeros schedule install`), quiet hours, pause/resume,
      one pending catch-up for missed slots, weekly prune, run-log retention
- [x] `careeros storage` (bytes by category, snapshots) + `careeros advise` / `advise apply <id>` (suggest-only)
- [ ] SQLite run index (`data/careeros.db` `runs` table) for the UI, rebuilt from `data/runs/` (`docs/UI.md`)
- [ ] Scheduled apply path: honour `runs.auto_submit.enabled`, gated by the daily cap (`careeros run cap --check`)
      and `auto_submit_decision` (Tier A and non-pass safety always manual); off by default
- [ ] Finish the inbox-sync skill, then set `schedule.jobs.inbox_sync.enabled: true` (the job, 08:00 + 18:00 with a
      Gmail MCP auth preflight, is already in the scheduler). Follow-ups in the scheduler: still to do
- [ ] `/schedule` cloud routines as an alternative to the LaunchAgent (runs while the Mac is off; needs the repo and
      data reachable from the cloud session) for scout + inbox-sync
- [ ] Weekly self-review report: acceptance rate by category/tier, QA fail reasons, time saved
- [ ] P1.5 scout source: Simplify New-Grad GitHub list parser (public, ATS links)
- [ ] P7 chrome discovery: Jobright + Handshake feeds (saved-search URLs → `config/companies.yaml: searches`)
- [x] `careeros doctor`: validate the candidate's own config/profile against the example schema, fail on
      untouched example data; `docs/GETTING_STARTED.md`

## Future (not now)
- [ ] Action Items redesign: group by `Type` + `Needs` column = `laptop` (Chrome/Handshake/Workday session, candidate present) | `phone` (approve/send from anywhere) | `anytime`; sort by Priority then NextActionDate; separate "Today" view. Tier A submits, Handshake, Workday review pages = `laptop`. LinkedIn sends, email approvals, cover-letter reviews = `phone`.
- [ ] Handshake apply sessions: candidate logged in + present; system drives Chrome, candidate debugs live. Assisted mode only.
- [ ] Web UI dashboard (jobs pipeline, action items, contacts, stats). Design spec: `docs/UI.md`. Action Items section: every item shows its `Link` as a clickable hyperlink (e.g. "review & submit" opens the prepared application form) — reads tracker/data; likely local FastAPI + simple frontend, or Artifact page fed from tracker.
- [ ] Phone access: approve/reject drafts, mark actions done, get interview alerts. Candidates: Google Sheet mirror of tracker, push notifications (already planned), Claude Code remote sessions, or the web UI made mobile-first.

## Ghost jobs
- [x] Old (30 info / 45 review), skip only when old + not updated + company not posting + not evergreen/senior;
      reposted (3+ requisitions in 90 days, edits counted separately); aggregator-only; freeze covering the role
      (review) / layoffs (info). `src/careeros/safety/ghost.py`, `data/posting_history.json`, `careeros safety signal`.
- [ ] Tracker `PostedDate` column (needs a Jobs-sheet column migration like Action Items `Needs`).

## Safety — scam / data-harvesting protection
- [x] Safety verdicts Pass / Review / Block with reason codes + evidence (`careeros safety check|fields`, `src/careeros/safety/scam.py`); per-code levels in `targets.yaml: safety.levels`. Unknown companies = review, not suspicious; `careeros safety verify --risk low|medium|high` from independent signals. Registry entries carry confidence, evidence, expiry and `careeros safety clear`. Made-up companies: anything off the curated lists is `company_unverified` (no auto-submit) until /score-job verifies it (`careeros safety verify`); brand look-alikes on foreign domains are a hard stop. Hard stops (→ Action Item, never auto):
      any field asking SSN / DOB / bank / passport / driver's license / ID upload / mother's maiden name; pay-to-apply or "training fee";
      apply URL domain ≠ company domain and ≠ known ATS (greenhouse/lever/ashby/workday/icims/smartrecruiters/…); contact email on free domain (gmail/outlook/yahoo);
      company has no resolvable website / LinkedIn page / < N employees; posting text hits scam patterns (WhatsApp/Telegram interview, "hiring immediately, no interview", crypto wallet, check-cashing, "equipment reimbursement");
      salary wildly above market for level. Soft flags lower fit score and require review.
- [x] Allowlist (`auto_submit_allowed`, `safety.json`): auto-submit only on the ATS families in `targets.yaml: safety.auto_submit_ats` reached from a company-owned domain or the company's ATS board (scout-sourced). Postings from aggregators (Jobright/Handshake/LinkedIn) must resolve to that before auto.
- [x] Data minimization (`answer_for`: optional street blank; `sensitive` labels never answered): applier never enters anything not in `standard_answers.yaml`; address = city/state/zip only unless required by a verified ATS; phone/email are the only PII given by default.
- [x] `detection.yaml`-style registry for flagged companies/domains (`data/flagged_registry.yaml`, `careeros safety flag`), consulted by scout to drop future postings.
