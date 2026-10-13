# Tasks
Status lives in trace.yaml. Order = build order; USR-033 (TASK-001..003) first. Each ≤40 builder calls.

### TASK-001 Untrusted wrapping + per-kind tools
Links: REQ-108 · Area: backend · Done when: prompt builder wraps posting/JD/email in `<untrusted source=…>`; skills carry the rule; score/review/edit argv has no web tools; prepare gets WebSearch + `WebFetch(domain:<company>)`. SEC-01 green

### TASK-002 Injection scan + flags.json + block
Links: REQ-109 UC-012 · Area: backend · Done when: `untrusted.scan` in `Store.save_posting`; flags.json; Action Item; `eligibility` blocks prepare/apply (exit 2 `injection suspected`); `careeros job clear-injection <id>`. E2E-012-01 green

### TASK-003 QA untrusted_content hard check
Links: REQ-110 UC-012 · Area: backend · Done when: qa hard fail on emails/URLs/phones/names not in profile+posting and instruction echo; regen once then Action Item. E2E-012-02 green

### TASK-004 Shared terms + text extraction + ATS view
Links: REQ-098 · Area: backend · Done when: `careeros.terms` (moved from qa), `careeros.extract` pdf/docx/txt (DEC-001), ats.json fields + warnings; deterministic test

### TASK-005 Readiness module + exit 7 gate
Links: REQ-102 REQ-103 · Area: backend · Done when: `readiness.items/require_ready`; doctor reuses it; `GET /api/readiness`; every apply path exit 7 / 409. ACCEPT-103 green

### TASK-006 Job `selected` flag
Links: REQ-104 · Area: backend · Done when: new postings selected=false, legacy missing=true, `--job` selects; runs/batch/tick filter; `careeros job select|unselect`, `POST /api/jobs/select`

### TASK-007 Résumé store + API
Links: REQ-093 REQ-099 REQ-100 UC-001 · Area: backend · Done when: profile/resumes layout (DEC-008), raw-body upload (DEC-006), list/versions/delete rules, types incl. one master; CLI `resume list|add`

### TASK-008 Review run + feedback lifecycle
Links: REQ-094 REQ-095 REQ-096 REQ-097 UC-002 FLOW-002 · Area: backend · Done when: run kinds review/resume_edit, skills review-resume/edit-resume, apply guard (reuse qa numbers/tools) 422 on fail, comment redraft, hand edit = new version

### TASK-009 Set master → master.yaml diff
Links: REQ-099 UC-003 · Area: backend · Done when: extract-master skill → master.proposed.yaml; approve/reject API; readiness open while pending

### TASK-010 Match score + matches API
Links: REQ-111 REQ-115 · Area: backend · Done when: DEC-003 formula, synonyms config, `GET /api/jobs/{id}/matches`, `careeros resume match <job>`. ACCEPT-111 green

### TASK-011 Résumé pick: reuse / tweak / tailor
Links: REQ-112 REQ-113 UC-011 · Area: backend · Done when: `resume pick` writes resume_choice.json before prepare-job; skill obeys; tailored saved as `tailored` résumé; DEC-007 QA skip. E2E-011-01 green

### TASK-012 Check a job
Links: REQ-114 REQ-116 UC-010 FLOW-003 · Area: backend · Done when: `POST /api/jobs/check` paste/file, scan, score run, match table, one tailor offer, below_threshold keep/discard. E2E-010-01/02 green

### TASK-013 Profile page UI
Links: REQ-107 REQ-101 REQ-102 UC-005 UC-006 FLOW-001 · Area: frontend · Done when: sections Résumés, Writing samples (learn-voice rerun), Saved answers, Learned, Readiness card on Today+Profile; snapshots updated
DEC-022 change → TASK-036 (setup card on Today).

### TASK-014 Fill preview + ask unknown
Links: REQ-105 REQ-106 · Area: frontend · Done when: fill plan table edit + save-to-profile; needs_input prompt / Action Item; required unanswered blocks fill

### TASK-015 Jobs list: select, badges, check dialog
Links: REQ-104 REQ-109 REQ-114 REQ-115 · Area: frontend · Done when: checkbox + bulk select, injection badge + I checked it, Check a job dialog, résumé match table on job detail
DEC-022 change → TASK-035 (select/badges/check dialog move into Saved › List).

### TASK-016 Per-job stop point in batches
Links: REQ-118 UC-013 · Area: backend · Done when: batch `stops` map + `--job-stop`; API accepts `stops`; server-side caps (Tier A, LinkedIn, readiness, injection); old batches unchanged. E2E-013-02 green

### TASK-017 Start pipeline sheet
Links: REQ-117 REQ-120 UC-013 FLOW-004 · Area: frontend · After: TASK-015, TASK-016 · Done when: Start pipeline button (disabled reason), review sheet on the Jobs table with "Go as far as" + per-row override + cap reasons, Start → batch progress; tour gains a Start pipeline step (REQ-121). E2E-013-01 green
DEC-022 change → TASK-035 (Start pipeline on Saved tab).

### TASK-018 Page guidance on every page
Links: REQ-119 REQ-120 · Area: frontend · Done when: every route has h1 + guidance line + primary action; empty states with button; test enumerates routes; job lists reuse the Jobs table

### TASK-019 First-run tour + How to use
Links: REQ-121 UC-014 · Area: full · Done when: `GET/PUT /api/ui-state` (tour_done, `data/ui_state.json`, atomic); overlay tour, skip/Esc, keyboard, focus return; Settings "How to use". E2E-014-01 green
DEC-022 change → TASK-037 (tour steps, nav).

### TASK-020 Next-step card
Links: REQ-122 UC-014 · Area: full · Done when: `GET /api/next-step` rule order per REQ-122 (unit tests per rule); Today card + Profile once on readiness done. E2E-014-02 green
DEC-022 change → TASK-036 (card removed, E2E-014-02 rewritten).


### TASK-021 Voice samples accept pdf + docx
Links: REQ-101 · Area: full · After: TASK-013 · Done when: `voice.py` EXTS and UI accept list include .pdf/.docx; docx converted to plain text (stdlib zipfile+xml, no new dep) and stored as .txt; pdf stored as-is and read by learn-voice (extract text if a test shows Read cannot); size cap; unit test for docx extraction (tiny fixture in tests/fixtures) + upload integration test; learn-voice run uses their text

### TASK-022 Résumé feedback + master approve/reject UI
Links: REQ-094 REQ-095 REQ-096 REQ-097 REQ-099 · Area: frontend · After: TASK-013 · Done when: Profile page panel shows proposed master.yaml diff and résumé feedback (TASK-008/009 backend); Approve / Reject buttons call the existing endpoints; readiness card links to the panel when master is not synced and updates after approve/reject; UI_UX_PRINCIPLES applied; vitest + API integration test; before MVP

### TASK-023 AI draft answers in fill plan (review gate)
Links: REQ-105 UC-008 · Area: full · After: TASK-014 · Done when: `build_plan` reads the job's `answers.json` drafts for freetext fields with no saved answer (never legal/salary/EEO), source `ai_draft`, `reviewed: false`; `plan_problems` blocks fill on unreviewed drafts; approve endpoint + edit marks reviewed; carry_over keeps review state; Fill preview shows "AI draft" badge + Approve; save-to-profile off for drafts; CLI/scheduled one Action Item "review N drafts"; unit + integration tests (E2E-008-01 extended); before MVP

### TASK-024 Résumé hand editor + applied-edit diff/undo UI
Follow-up from TASK-022 review: Profile › Résumés hand editor with Save (`PUT /api/profile/resumes/{rid}/text`, REQ-097) and, after Apply, the new version's diff with undo = open the previous version (REQ-095). Status: superseded by TASK-027..033 (résumé workspace, DEC-012..019).

### TASK-025 Check-a-job dialog: Prepare application + Why this score
Links: REQ-114 REQ-116 UC-010 FLOW-003 · Area: full · After: TASK-015 · Done when: result shows primary "Prepare application" (ticks job + starts prepare run) and secondary "Cancel" (job kept, unticked); "Done" / "Keep job, no résumé" / separate "Tailor from master" removed; below-threshold keep/discard kept; `GET /api/jobs/{id}/matches` exposes per-résumé matched + missing keywords (required vs preferred, from match.py `hit`); match table "Why this score" toggle; unit + API integration + vitest; E2E-010-01 updated. Status: done

### TASK-026 Action Items to data/action_items.json
Links: REQ-123 REQ-052 REQ-073 · Area: backend · Done when: store in `data/action_items.json` (atomic write like status.json), CLI/UI/API read it, one-time import from the xlsx sheet, xlsx Action Items sheet written json → xlsx only on sync; unit + integration tests. Status: todo (not built)

### TASK-027 Résumé schema v1 + migrate on read
Links: REQ-124 · Area: backend · Done when: one schema = `data/jobs/<id>/resume.json` shape + `schema_version` + résumé-local ids + optional `source` (master.yaml id) (DEC-018); `careeros.resumes.read_resume_json` / `migrate` read old files and migrate in memory; render.py/qa accept it; QA bullet_fidelity only on `source` bullets; unit tests (migrate, ids stable) + render integration test. Status: done (migration in `careeros.resumes.migrate`/`read_resume_json`; QA reads a trace view; pre-v1 id-less bullets still fail bullet_fidelity)

### TASK-028 Draft API: autosave + stale-write 409
Links: REQ-126 UC-002 · Area: backend · After: TASK-027 · Done when: `profile/resumes/<rid>/draft.json` with `rev`; `GET/PUT /api/profile/resumes/{rid}/draft` (PUT with old `rev` → 409); atomic write; "Draft" status = hash(draft) ≠ hash(latest) (DEC-014); stale temp-dir cleanup on startup; unit + API integration tests; DEC-018 amendment: a draft write may set bullet `origin: "user"` only for a user-authored edit (`author: user`), never from an AI write Status: done (`careeros.resumes.get_draft`/`put_draft`; `rev` int, sha256 of canonical JSON vs latest `v<n>/resume.json`; origin guard `_check_origin`: AI write keeps only marks the previous draft had on the same id+text, else 422; `cleanup_tmp` on UI startup removes `*.tmp` older than 10 min)

### TASK-029 Change log + revert
Links: REQ-126 UC-002 · Area: backend · After: TASK-028 · Done when: every draft write appends `draft.changes.jsonl` `{id, at, author, target_id, op, before, after, reverts?}`; `POST .../draft/changes/{id}/revert` = inverse change, refused (409 with both texts) when target no longer holds `after` (DEC-015); E2E-002-06 green; DEC-018 amendment: `origin: "user"` is tamper-proof only when `changes.jsonl` shows a user change created/last edited that bullet text (DEC-020); QA/apply gate checks it Status: done (`careeros.resumes` `_commit` logs per-node changes under `_locked` after the atomic draft write: `kind` bullet|entry|field, `target_id` = bullet/entry id or top-level key, `op` add|edit|delete, `before`/`after` = node (entry without bullets), `where` for re-insert; order-only moves not logged; `revert_change` → `Conflict` 409 `{expected, current}`; `user_texts` replays the logs: per bullet, the author of the last line that changed its text (unchanged-text lines keep the prior author; a revert inherits the restored text's author; unparsable lines skipped = fail closed); known DEC-018 limit: `PUT .../draft` `author` is client-supplied; `qa.check_bullet_fidelity` counts `origin: "user"` only for those texts of `resume_choice.json` `rid`; E2E-002-06 backend half covered by `test_change_log_and_revert_api`, UI half lands with TASK-033)

### TASK-030 Annotations: suggestions, comments, replies, accept
Links: REQ-095 REQ-126 UC-002 · Area: backend · After: TASK-029 · Done when: `annotations.json` replaces review.json items (migrate); statuses open/accepted/rejected/outdated; accept runs the apply-edit base check + zero-fabrication guard, then a draft change author=ai; reply with "Apply comment" queues an AI re-draft run, AI only proposes/replies (DEC-016); `review-resume`/`edit-resume` skills write annotations; unit + integration tests; E2E-002-05 green; DEC-018 amendment: accepting an AI suggestion clears `origin` (the bullet then needs a valid `source`)
Note: accept does not check `source` (uploaded base bullets carry none); QA `bullet_fidelity` enforces it for tailored résumés.

### TASK-031 Publish: one version per Next/Done
Links: REQ-126 UC-002 · Area: backend · After: TASK-030 · Done when: `POST .../publish` (idempotency key) writes `v<n+1>/resume.json` in a temp dir → rename → meta.json; unchanged hash = no-op; `draft.changes.jsonl` moved to `v<n+1>/changes.jsonl` (DEC-017); no text/ATS/.tex/PDF stored per version: store helper renders them on demand and existing readers (match, review) use it; PDF cached for latest only, keyed by hash + renderer version (DEC-020); same JSON → identical text/.tex; annotations carried or `outdated`; crash-between-steps integration test; E2E-002-07 green

### TASK-032 Import run + verbatim guard
Links: REQ-124 UC-001 · Area: backend · After: TASK-027 · Done when: every upload runs extract-master as the single import (DEC-019) → v2 structured; guard: every bullet appears whitespace-normalised in v1 text.txt; fail → `import.json` failed + Action Item, v1 kept, Retry endpoint; "Not carried over" list + Restore (adds to draft); E2E-001-03/04 green; DEC-018 amendment: the import guard (DEC-019) is the only path that sets `origin: "user"` on uploaded bullets (verbatim in `text.txt`)

### TASK-033a Workspace UI `/resumes/<rid>`: render, edit, autosave, publish
Links: REQ-125 REQ-126 UC-002 · Area: frontend · After: TASK-028..031 · Done when: page per `mockups/resume-workspace.html`: HTML render with inline suggestions, aligned margin cards, reply threads, in-place edit of structured fields, autosave (500–800 ms debounce, flush on navigation, pagehide sendBeacon), "Saving…/All changes saved", Next/Done → publish; ships TASK-030 part B; UI_UX_PRINCIPLES applied; vitest + UI bundle rebuilt; E2E-002-01 green
Deferred from 033a:
- ATS view tab.
- Open-suggestions count.
- Onboarding "Next" (PublishIn.master).
- Apply-comment run_id + annotation polling (DEC-011/P10).
- Render all schema fields (stack/links/coursework/activities, skill_groups).
- Per-run annotation count in step.py (needs run_id via `resume annotate`).
- Firefox/Safari field-sizing fallback.
Note: split from TASK-033 (user, 2026-10-12) so the page ships in parallel with TASK-032. pagehide uses `fetch(..., {keepalive: true})` PUT, not sendBeacon: sendBeacon can only POST and cannot send the `X-CareerOS` write header (403). E2E-002-01: backend half covered by TASK-030/031 tests; no browser E2E harness for the UI half yet.

### TASK-033b Workspace history, undo, résumé row statuses
Links: REQ-125 REQ-126 UC-001 UC-002 · Area: frontend · After: TASK-032, TASK-033a · Done when: History with Revert, ⌘Z client undo; Profile › Résumés row status Reviewing/Draft/Ready/Failed; "Not carried over" list + Restore; UI_UX_PRINCIPLES applied; vitest + UI bundle rebuilt
API (033b): `GET /profile/resumes` rows carry `status`, first match wins: `failed` = import.json or the review failed (Retry); `reviewing` = import or review running; `draft` = unpublished draft (draft ≠ latest) or no structured version yet; else `ready`. Apply comment (`POST .../feedback/{fid}/comment`, `POST .../annotations/{aid}/replies` with `apply`) returns `run_id`; annotations and replies written by `resume annotate`/`annotate-reply` inside a run carry `run` (CAREEROS_RUN_ID); `GET .../annotations?run=<id>` lists the annotations that run created or replied to (poll it with the run's state); step.py fails a completed Apply/review run that wrote nothing under its own run id (pre-run count fallback when no run id). Open-suggestions count: UI counts from the annotations list, no API. ATS view: `GET /profile/resumes/{rid}/draft/text` = resume.txt rendered on demand from the current draft (DEC-020); no client-side approximation. Onboarding: Next replaces Done while the master résumé is `draft`; `?onboarding=1` forces it (first-run testing).
- DEC-021 QA preflight before reuse (fluff #18): `qa.preflight_resume` + `match.pick` gate + `preflight.json` cache; short QA failure display with Tailor instead.

### TASK-034 Job buckets + reasons line (backend)
Links: REQ-127 REQ-128 REQ-130 UC-015 UC-016 · Area: backend · Done when: `TABS` = recommended/saved/applied with clauses per 09 Delta 2026-10-13; old tab keys mapped, not 400; `GET /api/today` gains `top_picks` from the same clause; `GET /api/jobs` rows carry `reasons` from `match.matches` for returned rows only (résumé texts loaded once per request); unit: top picks ⊆ recommended, counts == rows, match call count == page size; OpenAPI regen

### TASK-035 Jobs tabs + List / Table / Board (frontend)
Links: REQ-128 REQ-129 REQ-130 REQ-132 REQ-104 REQ-117 UC-013 UC-016 FLOW-004 · Area: frontend · After: TASK-034 · Done when: tabs with counts; List (cards: fit + reasons line), Table (existing), Board on Applied with drag → `POST /api/jobs/{id}/status`, snap back + reason on refusal; `ui.jobs_view` in `/api/ui-state`; select/badges/check dialog + Start pipeline on Saved; colour only for meaning (REQ-132); UI_UX_PRINCIPLES applied; vitest + UI bundle rebuilt. E2E-016-01..05 green

### TASK-036 Today: Top picks + setup card
Links: REQ-127 REQ-131 REQ-102 UC-014 UC-015 FLOW-005 · Area: frontend · After: TASK-034 · Done when: setup card (REQ-102 readiness as data) until done, then Top picks band; click opens the job in Jobs; Next-step card + `GET /api/next-step` removed (REQ-122 deprecated); E2E-015-01..05 green, E2E-014-02 rewritten

### TASK-037 /pipeline redirect + nav + tour
Links: REQ-129 REQ-121 UC-014 UC-016 · Area: full · After: TASK-035 · Done when: `/pipeline` → `/jobs?tab=applied&view=board` (308); Pipeline nav item removed; tour steps name the new nav; `GET /api/pipeline` removed once the Board no longer reads it; route test enumerates the redirect
