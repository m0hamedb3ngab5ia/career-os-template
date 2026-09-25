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
- [ ] P6 custom scrapers for `ats: custom` boards (company career pages without a public ATS API)
- [ ] P7 LinkedIn Jobs discovery (never Easy Apply)
- [ ] Workday adapter (assisted mode)
- [ ] `/schedule` cloud routines for scout + inbox-sync
- [ ] Weekly self-review report: acceptance rate by category/tier, QA fail reasons, time saved
- [ ] P1.5 scout source: Simplify New-Grad GitHub list parser (public, ATS links)
- [ ] P7 chrome discovery: Jobright + Handshake feeds (saved-search URLs → `config/companies.yaml: searches`)
- [x] `careeros doctor`: validate the candidate's own config/profile against the example schema, fail on
      untouched example data; `docs/GETTING_STARTED.md`

## Future (not now)
- [ ] Action Items redesign: group by `Type` + `Needs` column = `laptop` (Chrome/Handshake/Workday session, candidate present) | `phone` (approve/send from anywhere) | `anytime`; sort by Priority then NextActionDate; separate "Today" view. Tier A submits, Handshake, Workday review pages = `laptop`. LinkedIn sends, email approvals, cover-letter reviews = `phone`.
- [ ] Handshake apply sessions: candidate logged in + present; system drives Chrome, candidate debugs live. Assisted mode only.
- [ ] Web UI dashboard (jobs pipeline, action items, contacts, stats) — reads tracker/data; likely local FastAPI + simple frontend, or Artifact page fed from tracker.
- [ ] Phone access: approve/reject drafts, mark actions done, get interview alerts. Candidates: Google Sheet mirror of tracker, push notifications (already planned), Claude Code remote sessions, or the web UI made mobile-first.

## Safety — scam / data-harvesting protection
- [ ] Scam gate in score-job + apply-job, before any form fill. Hard stops (→ Action Item, never auto):
      any field asking SSN / DOB / bank / passport / driver's license / ID upload / mother's maiden name; pay-to-apply or "training fee";
      apply URL domain ≠ company domain and ≠ known ATS (greenhouse/lever/ashby/workday/icims/smartrecruiters/…); contact email on free domain (gmail/outlook/yahoo);
      company has no resolvable website / LinkedIn page / < N employees; posting text hits scam patterns (WhatsApp/Telegram interview, "hiring immediately, no interview", crypto wallet, check-cashing, "equipment reimbursement");
      salary wildly above market for level. Soft flags lower fit score and require review.
- [ ] Allowlist: auto-submit only on the ATS families in `targets.yaml: safety.auto_submit_ats` reached from a company-owned domain or the company's ATS board (scout-sourced). Postings from aggregators (Jobright/Handshake/LinkedIn) must resolve to that before auto.
- [ ] Data minimization: applier never enters anything not in `standard_answers.yaml`; address = city/state/zip only unless required by a verified ATS; phone/email are the only PII given by default.
- [ ] `detection.yaml`-style registry for flagged companies/domains (`data/scam_registry.yaml`), consulted by scout to drop future postings.
