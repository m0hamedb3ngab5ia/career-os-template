# Requirements
Status lives in trace.yaml. Reconstructed by `/product audit` 2026-10-04: all `proposed` until triage.
Format: `### REQ-NNN title`, 1 line, provenance, Evidence, Tests. Given/When/Then added when approved.
Areas: [Setup & privacy](#setup--privacy) · [Scout & safety](#scout--safety) · [Prepare & QA](#prepare--qa) · [Apply](#apply) · [Runs & schedule](#runs--schedule) · [Tracker, actions, learning](#tracker-actions-learning) · [Outreach & inbox](#outreach--inbox) · [Local UI](#local-ui) · [Ops](#ops) · [NFR](#non-functional)

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
Off by default; Tier A + non-pass safety always assisted; `manual: [tier_a, fit_gte_85]`; allowlisted ATS on own domain only.
contradictory (Q-003) · Evidence: src/careeros/runs/policy.py:25,134-144, safety/scam.py:338 vs README.md:44 · Tests: tests/test_runs_policy.py
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
inferred, not built · Evidence: TODO.md:33

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
contradictory (Q-005) · Evidence: ARCHITECTURE.md:32 vs UI "sending shown off" docs/UI.md:8
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
`/kit` dev showcase ships to users.
observed · Evidence: ui/src/app/routes.tsx:28 · (decision-needed Q-006)
### REQ-079 Phone-width layout + phone companion
inferred, deferred · Evidence: docs/UI.md:21, TODO.md:49

## Ops
### REQ-090 Retention prune
Screenshots of closed jobs, stub unprepared postings, run logs/summaries; plan then `--yes`.
observed · Evidence: src/careeros/retention.py:38-44,150,236 · Tests: tests/test_retention.py
### REQ-091 Storage report + advisor
Suggest-only; `advise apply <id>` round-trips YAML, rolls back on failure.
observed · Evidence: ARCHITECTURE.md:240-252 · Tests: tests/test_advisor.py
### REQ-092 Weekly self-review report
inferred, not built · Evidence: TODO.md:39

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
