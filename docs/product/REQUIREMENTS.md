# Requirements (technical)
Derived from USER_REQUIREMENTS.md (the human layer; start there). Agent-facing detail.
Status lives in trace.yaml. Reconstructed by `/product audit` 2026-10-04: all `proposed` until triage.
Format: `### REQ-NNN title`, 1 line, provenance, Evidence, Tests. Given/When/Then added when approved.
Areas: [Setup & privacy](#setup--privacy) · [Scout & safety](#scout--safety) · [Prepare & QA](#prepare--qa) · [Apply](#apply) · [Runs & schedule](#runs--schedule) · [Tracker, actions, learning](#tracker-actions-learning) · [Outreach & inbox](#outreach--inbox) · [Local UI](#local-ui) · [Ops](#ops) · [Onboarding & profile](#onboarding--profile) · [NFR](#non-functional)

## Functional

## Setup & privacy
### REQ-001 Init from example or private link
`careeros init` copies `examples/` → `profile/`,`config/` (never overwrites) or `--link` symlinks from private dir; other cmds refuse until init.
observed · Evidence: src/careeros/bootstrap.py · Tests: tests/test_bootstrap.py
### REQ-002 Doctor setup checklist
`careeros doctor` FAILs on untouched example data, broken YAML, unknown bullet ids, invalid bold markup, no `claude`; exit 1; prepare/apply run it first.
observed · Evidence: src/careeros/doctor.py:619 · Tests: tests/test_doctor.py
### REQ-003 Personal data never committed
`profile/ config/ data/ CLAUDE.local.md .reviews/` gitignored; examples use fictional candidate.
observed · Evidence: .gitignore, .agent/DECISIONS.md · Tests: tests/test_examples.py
### REQ-004 Template sync guard
`careeros sync status|pull|install-hook` reports drift vs public template (0 sync/1 behind/2 drift/3 conflict); hook blocks personal paths.
observed · Evidence: src/careeros/sync.py:43,123 · Tests: tests/test_sync.py

## Scout & safety
### REQ-010 Scout ATS boards
Pull Greenhouse/Lever/Ashby boards from `companies.yaml`, store `data/jobs/<id>/posting.json`, sync tracker.
observed · Evidence: src/careeros/scout/ · Tests: tests/test_scout.py, tests/test_adapters.py
### REQ-011 Configurable prefilters
Title keywords, seniority, blocked countries, blocklist, flagged companies, ghost jobs; each toggled in `targets.yaml: scout`.
observed · Evidence: README.md:23-27 · Tests: tests/test_prefilter.py
### REQ-012 Posting close date extraction
`closes_at` from Greenhouse deadline/metadata or description text; unknown = None.
observed · Evidence: ARCHITECTURE.md:77-80
### REQ-013 Scam verdict pass/review/block
Reason codes + evidence; per-code levels configurable; unknown company = review.
observed · Evidence: src/careeros/safety/scam.py:64,250 · Tests: tests/test_safety_scam.py
### REQ-014 Sensitive form fields hard stop
SSN/DOB/bank/passport/ID-upload fields → Action Item, never auto.
observed · Evidence: src/careeros/safety/scam.py:316
### REQ-015 Ghost job detection
Old/reposted/aggregator-only/freeze signals → info/review/skip.
observed · Evidence: src/careeros/safety/ghost.py:131 · Tests: tests/test_safety_ghost.py
### REQ-016 Flagged registry
Flag/verify/clear companies+domains with confidence, evidence, expiry; scout drops flagged.
observed · Evidence: src/careeros/safety/registry.py:99-177 · Tests: tests/test_safety_registry.py

## Prepare & QA
### REQ-020 Score job
`/score-job` → category, fit 0-100, tier A/B/C, hard-filter fails, prepare/skip.
observed · Evidence: .claude/skills/score-job/ · Tests: tests/test_skill_contracts.py
### REQ-021 Tailor résumé from bullet ids only
One page, bullets by id, numbers frozen, placeholders never used; LaTeX → pdf/txt; `**bold**` markup.
observed · Evidence: .claude/skills/tailor-resume/, templates/resume/render.py, src/careeros/markup.py · Tests: tests/test_templates.py, tests/test_markup.py
### REQ-022 Cover letter per tier rule
Voice from samples, ≥2 sourced company facts; Tier C none unless required.
observed · Evidence: .claude/skills/write-cover-letter/, ARCHITECTURE.md:121
### REQ-023 Answer form questions
Standard answers verbatim; essays from bullet ids; legal/sensitive/salary → needs_review.
observed · Evidence: .claude/skills/answer-question/ · Tests: tests/test_questions.py
### REQ-024 Deterministic QA hard checks
Truth trace, bullet fidelity, numbers/tools, banned phrases, confidential terms, contact, page count, keywords, bold markup.
observed · Evidence: src/careeros/qa.py:543 · Tests: tests/test_qa.py
### REQ-025 Extended QA
Wrong company, cross-doc consistency, outreach policy, PDF fidelity.
observed · Evidence: src/careeros/qa_ext/ · Tests: tests/test_qa_company.py, test_qa_consistency.py, test_qa_outreach_policy.py, test_qa_pdf_fidelity.py
### REQ-026 Critic review + one regeneration
`/qa-review` scores 5 dims; fail → regenerate once → Action Item.
observed · Evidence: .claude/skills/qa-review/, prepare-job
### REQ-027 Applications per company gate
Max 2 per company / 90 d, 30 d rejection cooldown, similar roles compete by fit then close date.
observed · Evidence: src/careeros/company_policy.py:167,399,432 · Tests: tests/test_company_policy.py

## Apply
### REQ-030 Greenhouse fill plan
`apply plan` → `fill_plan.json`; legal/salary/EEO unanswered pause; sensitive exit 3.
observed · Evidence: CLAUDE.md commands · Tests: tests/test_gh_schema.py
### REQ-031 Browser fill, never submits
`apply fill` stages plan via Playwright, reads back values → `fill_summary.json` + screenshot; tab kept open (detached CDP).
observed · Evidence: src/careeros/apply/ · Tests: tests/test_gh_fill.py, tests/test_apply_browser.py
### REQ-032 Submit at most once
Click persisted before submit; second session raises.
observed · Evidence: src/careeros/apply/session.py:123-138
### REQ-033 Auto-submit policy
Opt-in mode alongside assisted (Q-003). Off by default; Tier A + non-pass safety always assisted; `manual: [tier_a, fit_gte_85]`; allowlisted ATS on own domain only.
confirmed (Q-003; README.md:44 overstates today) · Evidence: src/careeros/runs/policy.py:25,134-144, safety/scam.py:338 vs README.md:44 · Tests: tests/test_runs_policy.py
### REQ-034 Assisted mode hand-off
Fill everything, upload docs, stage, `needs_review` + "review & submit" Action Item.
observed · Evidence: ARCHITECTURE.md:206-213
### REQ-035 Daily apply cap
`max_applications_per_day` × season multiplier; `run cap --check` exit 3.
observed · Evidence: src/careeros/runs/policy.py:22,60, cli.py:572
### REQ-036 As-submitted snapshot
`submitted/<stamp>/` frozen copy + manifest; retention never touches it.
observed · Evidence: src/careeros/apply/snapshot.py, retention.py:21 · Tests: tests/test_snapshot.py
### REQ-037 ATS credentials store
`creds set|get|list|rm`, file 0600 or keychain, min 8 chars, redacted in logs.
observed · Evidence: src/careeros/credentials.py:31,97,181 · Tests: tests/test_credentials.py
### REQ-038 Lever/Ashby/Workday adapters
Chrome adapters beyond Greenhouse; Workday assisted.
inferred, half-built · Evidence: TODO.md:11,18

## Runs & schedule
### REQ-040 Budgeted batch runs
`run score|prepare` presets, rank with `why`, one headless call/job, stop reasons, never applies.
observed · Evidence: src/careeros/runs/runner.py, ranking.py · Tests: tests/test_runs_runner.py, test_runs_ranking.py
### REQ-041 Pipeline + job locks
One pipeline lock (runs, scout, prune); per-job lock; stale takeover; exit 6 when held.
observed · Evidence: src/careeros/runs/locks.py:45,203 · Tests: tests/test_runs_locks.py, test_runs_shared_lock.py
### REQ-042 Retry once then Action Item
Only job-own failures count; usage/auth/cancel don't.
observed · Evidence: ARCHITECTURE.md:189-194 · Tests: tests/test_runs_failures_reset.py
### REQ-043 Scheduler tick + LaunchAgent
Every 15 min: scout 3 h, score 01:00, prepare 02:00, weekly prune; quiet hours; pause/resume.
observed · Evidence: src/careeros/runs/tick.py, schedule.py, launchd.py · Tests: tests/test_tick.py, test_schedule.py, test_launchd.py
### REQ-044 Missed-slot catch-up
Missed slots never auto-run; one pending record; `run catch-up` or `--dismiss`.
observed · Evidence: ARCHITECTURE.md:226-232 · Tests: tests/test_catch_up_cancel.py
### REQ-045 Batch across stages
`batch create --stop-at score|prepare|fill|submit`; LinkedIn excluded from fill/submit; one job per run.
observed · Evidence: src/careeros/runs/batches.py:72 · Tests: tests/test_runs_batches.py, test_runs_batch_driver.py
### REQ-046 Scheduled apply path
Scheduler honours `runs.auto_submit.enabled` gated by cap + decision.
confirmed, not built (Q-003) · Evidence: TODO.md:33

## Tracker, actions, learning
### REQ-050 Excel tracker, atomic, queued when locked
Jobs/Action Items/Contacts/Log tabs; ops queue to `.pending.json` if Excel open.
observed · Evidence: src/careeros/tracker.py · Tests: tests/test_tracker.py, test_tracker_cli.py
### REQ-051 Job status lifecycle
`found → scored → … → offer|rejected|withdrawn|ghosted`; status refuses locked job without token.
observed · Evidence: ARCHITECTURE.md:114, 187
### REQ-052 Action Items for uncertainty
`action add --type --needs laptop|phone|anytime`, due dates, done/reopen.
observed · Evidence: src/careeros/models.py:145 · Tests: tests/test_tracker_due.py
### REQ-053 Learn answers once
Answer on item / CLI → `standard_answers.yaml` (general, per-company, EEO); refuses empty/dup/examples path.
observed · Evidence: src/careeros/learning.py · Tests: tests/test_learning.py
### REQ-054 Apply lessons
Hurdles per ATS/company logged and read at next apply session.
observed · Evidence: src/careeros/learning.py, ARCHITECTURE.md:271-277

## Outreach & inbox
### REQ-060 Find contacts
Recruiter/HM/lead from posting + site, LinkedIn search URLs, email guesses w/ confidence.
observed (skill) · Evidence: .claude/skills/find-contacts/
### REQ-061 Draft outreach, never auto LinkedIn
Notes ≤300 chars; 1st-degree/mutuals → tailor manually; auto email only verified; thank-yous manual.
observed · Evidence: src/careeros/outreach.py:22-68, qa_ext/outreach_policy.py · Tests: tests/test_outreach.py
### REQ-062 Gmail auto-send after template confirmed
Rejected 2026-10-04 (Q-005): drafts only. confirmed · Evidence: ARCHITECTURE.md:32 vs UI "sending shown off" docs/UI.md:8
### REQ-063 Inbox sync
Classify Gmail mail, update tracker, push + Action Item on interview/assessment/offer.
inferred, half-built (scheduler job off) · Evidence: TODO.md:12,35 · Tests: tests/test_runs_inbox.py

## Local UI
### REQ-070 Local app, live index
`careeros ui` FastAPI + React on loopback; disposable SQLite index; watcher + SSE.
observed · Evidence: src/careeros/ui/app.py, index.py, watch.py · Tests: tests/test_ui_*.py
### REQ-071 Today page
observed · Evidence: ui/src/app/routes.tsx:12, routers/today.py · Tests: tests/test_ui_today_jobs.py
### REQ-072 Jobs list + detail actions
Tabs, facets, export, files, status/withdraw/submitted/override, safety verify/flag/clear, fill application.
observed · Evidence: src/careeros/ui/routers/jobs.py · Tests: tests/test_ui_job_pipeline.py
### REQ-073 Action Items page
Bulk done/reopen, answer, due, block/unblock company, mark-safe + undo.
observed · Evidence: routers/actions.py:65-147 · Tests: tests/test_ui_actions_service.py
### REQ-074 Pipeline + batch builder
observed · Evidence: routers/pipeline.py, batches.py · Tests: tests/test_ui_pipeline_service.py
### REQ-075 Automation (runs) page
Runs list/detail/stream, steps, cancel/pause/resume/catch-up, schedule control.
observed · Evidence: routers/runs.py · Tests: tests/test_ui_runs_service.py, test_ui_runs_view.py
### REQ-076 Settings without YAML
Schema-driven forms per section, diff, reset, ranking preview; storage & advise.
observed · Evidence: routers/settings.py, storage.py · Tests: tests/test_ui_settings_routes.py, test_settings_schema.py
### REQ-077 Contacts + Inbox pages (read + mark)
observed · Evidence: routers/contacts.py, inbox.py · Tests: tests/test_ui_contacts_inbox.py
### REQ-078 Component kit page in prod routes
`/kit` stays, hidden from nav (dev-only) (Q-006).
confirmed · Evidence: ui/src/app/routes.tsx:28
### REQ-079 Phone-width layout + phone companion
inferred, deferred (Q-004) · Evidence: docs/UI.md:21, TODO.md:49

## Ops
### REQ-090 Retention prune
Screenshots of closed jobs, stub unprepared postings, run logs/summaries; plan then `--yes`.
observed · Evidence: src/careeros/retention.py:38-44,150,236 · Tests: tests/test_retention.py
### REQ-091 Storage report + advisor
Suggest-only; `advise apply <id>` round-trips YAML, rolls back on failure.
observed · Evidence: ARCHITECTURE.md:240-252 · Tests: tests/test_advisor.py
### REQ-092 Weekly self-review report
inferred, not built · Evidence: TODO.md:39

## Onboarding & profile
New (Feature lane 2026-10-04, from USR-002..004, 022..027). Gate approved 2026-10-04; `(Q-0NN)` = answered question behind a choice.
All uploads + versions live under `profile/` (gitignored, REQ-003). One profile per install (USR-027).

### REQ-093 Upload résumé
Profile page has a Résumés section; accepts PDF or DOCX ≤5 MB (Q-009); stored with its original file.
Given Profile page · When user drops `cv.pdf` · Then file stored under `profile/resumes/<rid>/`, v1 (author=user) listed, review starts (REQ-094).
Failure: wrong type/too big → inline error, nothing stored. Corrupt/unreadable → stored, ATS view (REQ-098) warns "no text found".

### REQ-094 Background résumé review with progress
Upload starts one headless review run (skill, no API key); UI shows live progress; result = feedback items `{id, section, issue, suggestion}`.
Given upload done · When review runs · Then progress screen streams steps; on finish feedback list shows; user may leave page and come back.
Failure: `claude` missing/timeout → review state `failed` + Retry; upload kept. Events: run log like REQ-040.

### REQ-095 Apply feedback with one click
Apply → AI rewrites only the targeted section → new version (author=ai), diff shown, undo = open previous version.
Given feedback item · When Apply · Then new version vN+1 author=ai; item marked applied.
Guard: rewrite may not add numbers, employers, titles, dates or tools absent from the previous version (zero-fabrication, reuse qa fabrication check); violation → rejected, item stays open with reason.

### REQ-096 Comment on feedback
User comment on an item replaces one-click: AI re-drafts the suggestion using the comment (Q-010); user then Applies or Dismisses. Comments kept on the item.
Given item · When user comments "keep the Python line" · Then suggestion regenerated honoring comment; nothing written to résumé until Apply.

### REQ-097 Edit résumé by hand
In-app text editor on the parsed résumé content; Save → new version author=user. No guard (user owns facts).
Given v2 · When user edits a bullet + Save · Then v3 author=user, v2 unchanged.

### REQ-098 ATS view
Per version: plain text an ATS would read + parsed fields (contact, sections, roles+dates, skills) + warnings (images, tables, multi-column, missing contact, unreadable dates). Deterministic, no LLM.
Given uploaded PDF · When open ATS view · Then extracted text + fields + warnings shown; same input → same output.

### REQ-099 Résumé roles: master + others
Exactly one résumé is `master`; others get a type (`variant` | `other`, Q-011) and a name. Marking master demotes the old one.
Master feeds `profile/master.yaml`: on set-master (and on each new master version) AI extracts bullets → proposed `master.yaml` diff; user approves before write (Q-012). Numbers copied verbatim.
Given 2 résumés · When mark B master · Then A becomes `variant`, master.yaml diff proposed from B.

### REQ-100 Résumé list + version history
List all résumés (name, type, latest version, date). Per résumé: versions with author user|ai, time, source (upload/edit/feedback id). Open any version (view + ATS view). Delete non-latest versions; latest of master can't be deleted; deleting a whole résumé allowed unless master.
Given master v1..v3 · When delete v1 · Then v2,v3 remain · When delete v3 · Then refused with reason.

### REQ-101 Writing samples
Same Profile page: upload past cover letters / writing (txt, md, pdf, docx ≤5 MB) → `profile/voice/samples/`. List + remove. Any change re-runs `learn-voice` in background → `style_guide.md` Learned section. Cover letters use it; `voice_verified` true iff ≥1 sample.
Given 0 samples · When upload 2 · Then learn-voice runs once, list shows 2, next cover letter `voice_verified: true`.

### REQ-102 Readiness checklist
`GET /api/readiness` + UI card (Today + Profile) + `careeros doctor` reuse: items `{id, label, must, done, fix_link}`.
Must-haves (Q-013): master résumé set; master.yaml has no example/placeholder data (doctor); legal/work-auth + salary standard answers set; `claude` installed. Nice: ≥1 writing sample, ATS credentials, EEO answers.
Given fresh install · When open Today · Then checklist shows each item with link; all must-haves done → "Ready to apply".

### REQ-103 Apply blocked until ready
While any must-have open: `apply plan|fill`, `run apply`, batch stages fill|submit, scheduled apply refuse (CLI exit 7 + reason; UI buttons disabled with reason). Score/prepare not blocked (Q-013).
Given must-have open · When `careeros run apply --job X` · Then exit 7 "not ready: <items>", nothing filled.

### REQ-104 Pick jobs for pipeline
Job field `selected` (default false for every newly scouted job). Jobs list: checkbox per row, select all/visible, bulk tick/untick. Only selected jobs are ever prepared or applied (manual run, batch, scheduler). Scoring runs on all (Q-014). Untick later → excluded from future runs; a job mid-run finishes its current step then stops.
Given 10 scouted, 3 ticked · When `run prepare` · Then only those 3 prepared.

### REQ-105 Fill preview + edit
Before fill: UI table of the fill plan, per field: label, value, source (saved answer | AI draft | resume | default), required. User edits any value → plan updated (job only); checkbox "save to profile" also writes standard answer (REQ-053).
Given fill_plan · When user edits "Notice period" · Then fill uses edited value; `fill_summary` read-back matches.

### REQ-106 Ask on unknown fields
Plan field with no answer → `needs_input`; UI (and an Action Item for CLI/scheduled runs) asks: fill or skip. Skip allowed only for optional fields; required unanswered → job not filled. Filled answer saved to profile (REQ-053) unless user unticks save.
Never guessed: legal/salary/EEO stay hard rules (REQ-014, REQ-030).
Given plan with unknown required field · When user answers, save on · Then plan filled, `standard_answers.yaml` gains it, next job's plan auto-fills it.

### REQ-107 Profile page
One page, sections: Résumés (REQ-093..100), Writing samples (REQ-101), Saved answers (view/edit/delete `standard_answers.yaml`, incl. per-company + EEO), Learned (apply lessons view/delete, voice style summary), Readiness (REQ-102). All writes atomic via existing writers.
Given 12 saved answers · When delete one · Then gone from YAML and from future plans.

## Non-functional
### NFR-001 No API key; LLM only via Claude Code subscription
observed · Evidence: CLAUDE.md, .agent/DECISIONS.md
### NFR-002 Files canonical, written atomically; indexes disposable
observed · Evidence: ARCHITECTURE.md:237 · Tests: tests/test_runs_atomic.py
### NFR-003 UI loopback-only, Host/Origin checks, `X-CareerOS: 1` on writes, path-traversal-safe file serving
observed · Evidence: src/careeros/ui/security.py:13-42, services/job_actions.py:61-71 · Tests: tests/test_ui_security_events.py
### NFR-004 Tests never read private data or network
observed · Evidence: CLAUDE.md Testing
### NFR-005 macOS only (LaunchAgent, keychain)
inferred (Q-001)

## Constraints
- Never automate LinkedIn actions; never submit Tier A; never bypass qa-review; never fabricate. (CLAUDE.md hard rules)
- CI only in public template.
