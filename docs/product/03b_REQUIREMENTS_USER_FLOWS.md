# Requirements (technical): user flows
Second half of the REQ layer, split from 03_REQUIREMENTS.md at 400 lines (2026-10-13). Same format and rules as there; status lives in trace.yaml.

## Onboarding & profile
New (Feature lane 2026-10-04, from USR-002..004, 022..027). Gate approved 2026-10-04; `(Q-0NN)` = answered question behind a choice.
All uploads + versions live under `profile/` (gitignored, REQ-003). One profile per install (USR-027).

### REQ-093 Upload résumé
Profile page has a Résumés section; accepts PDF or DOCX ≤5 MB (Q-009); stored with its original file.
Given Profile page · When user drops `cv.pdf` · Then file stored under `profile/resumes/<rid>/`, v1 (author=user) listed, review starts (REQ-094).
Failure: wrong type/too big → inline error, nothing stored. Corrupt/unreadable → stored, ATS view (REQ-098) warns "no text found".
Changed 2026-10-12 (DEC-012): upload = v1 original file, read-only forever; then convert (REQ-124) → v2; review runs on v2. Upload lands in the workspace (REQ-125).

### REQ-094 Background résumé review with progress
Upload starts one headless review run (skill, no API key); UI shows live progress; result = feedback items `{id, section, issue, suggestion}`.
Given upload done · When review runs · Then progress screen streams steps; on finish feedback list shows; user may leave page and come back.
Failure: `claude` missing/timeout → review state `failed` + Retry; upload kept. Events: run log like REQ-040.

### REQ-095 Apply feedback with one click
Changed 2026-10-12 (DEC-012, wireframe). Accept (✓) → AI rewrite of the item's `quote` replaces it in place in the draft (REQ-126), shown as inline suggestion (deleted struck through, inserted in AI colour); card leaves margin → History. Reject (✕) same, text unchanged. Revert from History or ⌘Z. No version per accept.
Given feedback item · When Accept · Then draft text changed in place, item `accepted` (draft), entry in History, no new version until Next/Done.
Guard: rewrite may not add numbers, employers, titles, dates or tools absent from the previous version, nor stronger claims (scope, outcome, seniority verb e.g. supported → led) (zero-fabrication, reuse qa fabrication check); violation → rejected, item stays open with reason.

### REQ-096 Reply on feedback, optional Apply comment
Changed 2026-10-12 (Q-023): any card (suggestion or comment) has a reply thread, Google-Docs style. Reply box has checkbox "Apply comment": checked → reply sent to AI as feedback; it re-drafts the suggestion (or turns a comment into a suggestion) and posts a short reply. Unchecked → reply kept as a note, no AI run. Replies kept on the item, join the draft (REQ-126). Re-draft still a suggestion: nothing changes in the résumé until ✓.
Given suggestion · When user replies "keep the Python line" with Apply comment checked · Then suggestion re-drafted honoring it, thread shows reply + AI reply; résumé text unchanged until ✓.
Given card · When user replies with Apply comment unchecked · Then reply saved on card; no AI run.

### REQ-097 Edit résumé by hand
Changed 2026-10-12: edit text in place in the workspace (structured fields: bullets, headings, contact), never raw LaTeX. Edits join the draft (REQ-126), change tagged author=user. No guard (user owns facts).
Given v2 · When user edits a bullet + Next/Done · Then v3 holds the edit tagged user, v2 unchanged.

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
Changed 2026-10-12 (wireframe): in workspace, "All changes saved" opens version history panel: Current + versions newest first; select → read-only view, "Show changes" (inline diff vs previous), "Restore this version" (becomes draft, History cleared). No "Compare with…" (dropped). Any "new version" toast links to that version; never a bare "Applied vN". v1 (original upload) never deletable.

### REQ-124 Convert upload to structured résumé
After upload, AI converts v1 text into structured résumé (`resume_schema.md` shape: identity, sections, roles, bullets) → v2 author=ai source=convert, rendered with `templates/resume/default.tex` (PDF when LaTeX present) and HTML (REQ-125).
Guard: v2 may not add numbers, employers, titles, dates or tools absent from v1 text (REQ-095 guard). Dropped text (v1 lines not in v2) listed in a "Not carried over" panel; each line → Restore (adds to draft).
Given 1-page PDF · When convert · Then v2 structured, guard passes, dropped list shown (may be empty).
Failure: guard fails or no text → v2 not created, workspace shows v1 read-only + reason + Retry; review still runs on v1 text.

### REQ-125 Résumé workspace page
Changed 2026-10-12 (wireframe `mockups/resume-workspace.html`). Route `/resumes/<rid>`, full page. Header: "← Résumés" (back to Profile › Résumés, no confirm: autosaved) · name · "All changes saved" (REQ-100 history) · "↶ History (n)" · "N open" / "All handled" · one primary: onboarding → "Next: <next checklist step>" (first run: Saved answers), else "Done". Open items never block primary.
Body: résumé HTML render (our template look, no LaTeX) with inline suggestions; margin cards aligned to their text (Google Docs: active card level with its text, others stack without overlap). Click text ↔ card pairs both; hover card highlights its text. Card text = why, one line. Format-kind items (no quote) at top. AI comments (no rewrite) = yellow, ✓ resolve only.
Primary click → one version (REQ-126); onboarding also sets master (REQ-099) → next step.
Profile › Résumés keeps one row per résumé: name, role, status (Reviewing / Draft / Ready / Failed), one primary action linking to the workspace; errors inline banner + fix button. ATS view (REQ-098) = workspace tab.
Given review done with 3 items · When open workspace + click item 2 · Then item 2 text highlighted and card level with it, others not.
Given 2 of 4 items handled · When "Next: Saved answers" · Then new version, résumé master, Saved answers opens, 2 items still open on résumé.

### REQ-126 Autosaved draft, one version per Next/Done
Changed 2026-10-12 (wireframe). Accepts, rejects, resolves, restores and hand edits collect in one draft per résumé, autosaved server-side ("Saving…" → "All changes saved"), survives leaving page/restart. Each change records author (ai|user) + feedback id. History (n) lists handled items (Accepted/Rejected/Resolved/Restored + text), each Revert → item open again, any order; ⌘Z/⌘⇧Z undo/redo last change. No Save, no Discard (Revert / Restore version cover it).
Next/Done → one version vN+1 with per-change authors (label "you + AI" when mixed); handled items final, open items stay open for later. Leave via "← Résumés" or nav with changes → draft kept, Profile row status "Draft" until Next/Done. No changes → no draft, status unchanged.
Given draft with 2 accepts + 1 edit · When Done · Then exactly one new version, 3 changes tagged ai, ai, user; toast links to vN+1.
Given 1 accept · When "← Résumés" · Then row shows "Draft"; reopen → accepted text + History (1) restored.
Given accept then Revert in History · Then suggestion open again, text as before, History (0).

### REQ-101 Writing samples
Same Profile page: upload past cover letters / writing (txt, md, pdf, docx ≤5 MB) → `profile/voice/samples/`. List + remove. Any change re-runs `learn-voice` in background → `style_guide.md` Learned section. Cover letters use it; `voice_verified` true iff ≥1 sample.
Given 0 samples · When upload 2 · Then learn-voice runs once, list shows 2, next cover letter `voice_verified: true`.

### REQ-102 Readiness checklist
`GET /api/readiness` + UI card (Today + Profile) + `careeros doctor` reuse: items `{id, label, must, done, fix_link}`.
Must-haves (Q-013): master résumé set; master.yaml has no example/placeholder data (doctor); legal/work-auth + salary standard answers set; `claude` installed; master.yaml synced with master résumé (open while a REQ-099 diff is pending or rejected). Nice: ≥1 writing sample, ATS credentials, EEO answers.
Given fresh install · When open Today · Then checklist shows each item with link; all must-haves done → "Ready to apply".

### REQ-103 Apply blocked until ready
While any must-have open: `apply plan|fill`, `run apply`, batch stages fill|submit, scheduled apply refuse (CLI exit 7 + reason; UI buttons disabled with reason). Score/prepare not blocked (Q-013).
Given must-have open · When `careeros run apply --job X` · Then exit 7 "not ready: <items>", nothing filled.

### REQ-104 Pick jobs for pipeline
Job field `selected` (default false for every newly scouted job). Jobs list: checkbox per row, select all/visible, bulk tick/untick. Only selected jobs are ever prepared or applied (manual run, batch, scheduler). Scoring runs on all (Q-014). Untick later → excluded from future runs; a job mid-run finishes its current step then stops. Jobs existing before this change: missing field = true. Explicit `--job X` counts as selecting X.
Given 10 scouted, 3 ticked · When `run prepare` · Then only those 3 prepared.
Given pre-existing job without `selected` · When `run prepare` · Then it is prepared.
Amendment (Q-022, user-approved 2026-10-05): creating a batch counts as selecting its named jobs, like `--job X` (REQ-117).

### REQ-105 Fill preview + edit
Before fill: UI table of the fill plan, per field: label, value, source (saved answer | AI draft | resume | default), required. User edits any value → plan updated (job only); checkbox "save to profile" also writes standard answer (REQ-053).
AI draft = the job's `/answer-question` draft (`answers.json`) for a freetext field with no saved answer; never for legal/salary/EEO (REQ-014, REQ-030). Draft rows start unreviewed; fill refuses while any is unreviewed (like `needs_input`). Approve or edit marks it reviewed. "Save to profile" defaults off for drafts. CLI/scheduled: one Action Item "review N drafts". (DEC-010)
Given fill_plan · When user edits "Notice period" · Then fill uses edited value; `fill_summary` read-back matches.
Given plan with 1 unreviewed AI draft · When fill · Then refused; When user approves it · Then fill uses the draft text.

### REQ-106 Ask on unknown fields
Plan field with no answer → `needs_input`; UI (and an Action Item for CLI/scheduled runs) asks: fill or skip. Skip allowed only for optional fields; required unanswered → job not filled. Filled answer saved to profile (REQ-053) unless user unticks save.
Never guessed: legal/salary/EEO stay hard rules (REQ-014, REQ-030).
Given plan with unknown required field · When user answers, save on · Then plan filled, `standard_answers.yaml` gains it, next job's plan auto-fills it.

### REQ-107 Profile page
One page, sections: Résumés (REQ-093..100), Writing samples (REQ-101), Saved answers (view/edit/delete `standard_answers.yaml`, incl. per-company + EEO), Learned (apply lessons view/delete, voice style summary), Readiness (REQ-102). All writes atomic via existing writers.
Given 12 saved answers · When delete one · Then gone from YAML and from future plans.

## Job match & résumé reuse
### REQ-111 Résumé match score
Deterministic 0-100 per (résumé, job): weighted coverage of the JD's required/preferred skills + title/seniority terms by the résumé text (same parser as REQ-098 ATS view). No LLM, so all résumés can be compared cheaply. Threshold = setting `thresholds.min_match` (default 70, Q-015), overridable per check.
Given JD needing 10 skills, résumé covers 7 required · When scored · Then same score every run, breakdown lists 3 missing.
### REQ-112 Reuse before tailoring
Prepare step order: score all existing résumés (master, variants, earlier tailored ones) vs the job (REQ-111). Best ≥ threshold → reuse it (job links to that résumé version; no tailor run). Decision + reason logged in job dir.
Given variant "backend" scores 82, threshold 70 · When prepare · Then job uses "backend", no tailor skill call.
### REQ-113 Tweak only when worth it
Best < threshold: estimate gain from a tweak (swap/reorder ≤3 bullets from master.yaml by id; numbers frozen). Gain ≥ `thresholds.min_tweak_gain` (default 5) and reaches threshold → tweak, saved as new variant for that job category, reused by later jobs. Else full tailor from master (REQ-021). Never fabricate; only master.yaml bullets.
Given best 66, tweak estimate 74 · When prepare · Then one variant created, next similar job reuses it without a new run.
### REQ-114 Check any job (paste/upload)
Jobs page "Check a job": paste JD text or upload PDF/DOCX/txt (≤5 MB). Creates job `source: manual`, runs REQ-109 scan, REQ-020 fit score, REQ-111 per résumé. LinkedIn etc. text pasted by user allowed (user-side, Q-016).
Given pasted JD · When submit · Then job listed with fit score + per-résumé match table.
Result actions (2026-10-05): primary "Prepare application" (ticks the job, starts a prepare run: tailor from master + cover letter + QA) whether best is above or below threshold; secondary "Cancel" (job kept, not ticked). No "Done", "Keep job, no résumé" or separate "Tailor from master" button. Below-threshold keep/discard of the tailored résumé (REQ-116) stays. Match table has a per-résumé "Why this score" toggle: matched (✓) and missing keywords, required vs preferred, minimal; data from `GET /api/jobs/{id}/matches`.
Given result shown · When Prepare application · Then job ticked and prepare run started; When Cancel · Then job kept, unticked.
### REQ-115 Rank my résumés for a job
Job detail: table of every résumé with match score, best highlighted, threshold line, missing skills per résumé.
Given 3 résumés · When open job · Then sorted by match, best marked, scores = REQ-111.
### REQ-116 Below threshold → offer tailor, then report
No résumé ≥ threshold → offer "Tailor from master" (REQ-113/021). Result ≥ threshold → done. Still below → notice "threshold not met: best X, needed Y; missing: …" + ask "Create closest match anyway?" Yes → keep best attempt, marked `below_threshold`; No → discard attempt. Max one tailor run per check.
Given threshold 70, all résumés < 60, tailored = 64 · When check · Then notice shows 64/70 + missing skills, asks; Yes keeps it flagged.

### REQ-117 Start pipeline from the Jobs list
Jobs list "Start pipeline" button, enabled while ≥1 job ticked (REQ-104; disabled reason "Tick jobs first"). Opens a review sheet: one "Go as far as" for all ticked jobs (Prepare / Fill / Submit, default Fill = the user submits), override per row. Caps, each shown with its reason: LinkedIn Easy Apply (apply URL on linkedin.com) → Prepare, the user applies on LinkedIn (hard rule: never automate LinkedIn); a job found on LinkedIn whose apply URL is the company's own ATS follows the chosen stop like any job; Tier A → Fill (never Submit); readiness must-have open (REQ-103) → Prepare + link to Profile; injection flag (REQ-109) → excluded, with a warning icon whose hover (and keyboard focus) tooltip says why it was flagged (the matched rule, e.g. "hidden text asking to ignore instructions"). Start creates one batch (REQ-118) and opens its progress (per-job stage, Pause / Cancel / Retry). Only entry point for multi-job runs in the UI.
Given 4 ticked (plain, Tier A, LinkedIn Easy Apply, LinkedIn-found with Greenhouse URL) and default Fill · When Start pipeline · Then review shows Fill / Fill (Tier A, no Submit) / Prepare (Easy Apply, reason) / Fill (Submit offered).
### REQ-118 Per-job stop point in batches
Batch keeps `stop_at` (default for all) plus optional `stops: {job_id: stage}`; driver stops each job at its own stage. CLI `batch create … --stop-at S [--job-stop J=S ...]`; `POST /api/batches` accepts `stops`. Same caps as REQ-117 enforced server-side (a requested Submit on Tier A or fill/submit on LinkedIn Easy Apply is lowered with reason, never trusted from the client). Old batch files without `stops` behave as today. Amends REQ-045: the LinkedIn exclusion applies only to LinkedIn Easy Apply, keyed on the apply URL host, not the source board.
Given batch stop_at fill, stops {B: prepare, C: submit} · When run · Then A filled, B prepared only, C submitted only if auto-submit verdict allows.
### REQ-119 Page guidance line
Every page header: h1 + one short line saying what the page is for and the next thing to do, + its primary action (08_DESIGN_SYSTEM.md Page header). Empty states say what to do, with a button. Disabled buttons show why (UnavailableButton). Nav ≤6 items, plain names.
Given any route · When rendered · Then header has h1 + non-empty guidance line; no disabled button lacks a reason.
### REQ-120 Spreadsheet-style job tables
Every list of jobs (Jobs list, pipeline review sheet, batch progress) uses the current Jobs table: column header sort + filter menus, filter chips, pager rows 10/25/50/100, chosen size remembered (`ui.page_size`).
Given Jobs list · When choose 50 rows and reload · Then 50 rows shown; review sheet uses the same table.
### REQ-121 First-run tour
First open of the UI → short overlay tour, one step per main nav item + Start pipeline (≤8 steps), each pointing at its element with one line. Skip / Esc at any step ends it. Done or skipped → `tour_done: true` in `data/ui_state.json` (per install, not per browser); never shown again automatically. Settings "How to use" restarts it. Keyboard accessible, focus returns to the page.
Given fresh install · When open UI, skip at step 2, reload · Then no tour; Settings "How to use" shows it from step 1.
### REQ-122 Next-step card
Today shows one "Next step" card with one button, from the first rule that holds: readiness must-have open → "Finish setup" (link to first open item); no jobs → "Find jobs" (scout); no ticked jobs → "Pick jobs" (Jobs list); a batch running → "See progress"; else → "Start pipeline" (REQ-117). Also shown once on the Profile page when the last must-have closes.
Given ready, 12 jobs, 0 ticked · When open Today · Then card says "Pick jobs" and links to the Jobs list.
Deprecated 2026-10-13 (DEC-022): locked Today drops the Next step card. Setup branch → setup card (REQ-131); Find / Pick jobs → Top picks + its empty state (REQ-127); Start pipeline / See progress → Jobs › Saved (REQ-128, REQ-117). Profile one-time card: Q-029.
### REQ-123 Action Items stored in data/action_items.json
Action Items live in `data/action_items.json`, written atomically like `status.json` (NFR-002). The tracker xlsx Action Items sheet is a one-way synced view (json → xlsx only); edits in Excel are never read back. Amends REQ-052, REQ-073 (Q-008).
Given an Action Item added · When written · Then json updated atomically and xlsx sheet refreshed on sync; an Excel edit is overwritten.
Amendment (Q-022, user-approved 2026-10-05): "ticked" here = rows selected in the Jobs table. The batch takes the jobs it names, ticked or not, and creating it ticks them (REQ-104 `selected`); the dry-run preview changes nothing. Unticking a job mid-run holds it back from its next stage.

## Jobs on Today (DEC-022, 2026-10-13)
Mockup: `mockups/jobs-today.html`.

### REQ-127 Top picks band on Today
Band "Top picks for <role> in <city>" above Needs you: 3–5 new jobs (found ≤14 days, tier A/B; Q-025), best fit (REQ-020) first; never skipped, Saved or Applied. Heading says why picked + "Edit" link to search preferences (Q-026). Card = REQ-130 + primary Prepare (ticks job + one-job prepare run, as REQ-114) + Skip (status `skipped`, undo toast). Prepare disabled + reason while no master résumé.
Empty: no picks → "No new picks for <role> in <city>" + "Find jobs now" (scout); no preferences → "Tell us what you're looking for" + button to preferences.
Given 6 new scored jobs, 1 skipped, 1 Saved · When open Today · Then 4 cards, best fit first.
Given pick · When Prepare · Then job `selected`, prepare run for that job only, card "Preparing…", then job in Jobs › Saved.
Given pick · When Skip, then Undo · Then card back, status as before.
Failure: run fails → card stays: "Couldn't prepare: <cause>" + one fix (Retry / Tailor instead (DEC-021) / link to cause). FLOW-005.
### REQ-128 Jobs tabs with counts
`/jobs` tabs Recommended · Saved · Applied, each with count. Recommended = scored, not ticked, not skipped, not applied. Saved = ticked (REQ-104 `selected`), not applied yet, incl. preparing / prepared / filled; Start pipeline (REQ-117) lives here and runs on Saved. Applied = applied or later; stage sub-tabs Applied · Screening · Interview · Offer · Closed with counts (status mapping Q-028). Save = tick, Unsave = untick. Tab + stage in URL (`?tab=&stage=`).
Given 3 ticked, 2 applied (1 at interview) · When open `/jobs` · Then Saved (3), Applied (2), Applied › Interview (1).
### REQ-129 Jobs views: List, Table, Board
View toggle List | Table; Applied tab adds Board. `view=` in URL, last choice remembered (`ui.jobs_view`). List (default) = master-detail: compact cards (REQ-130) left, detail right, selected job = `/jobs/:id` (tab/view query kept), back/forward works; <900px list only, job opens full page. Table = REQ-120 unchanged. Board = Applied jobs in stage columns (sub-tabs as columns); card opens detail. Replaces Pipeline page (REQ-074).
Given `/pipeline` · When open · Then `/jobs?tab=applied&view=board`.
Given List view · When click 2nd job · Then URL `/jobs/<id>`, its detail on the right, list scroll kept; reload shows same job.
### REQ-130 Job card: fit score anchor + reasons
Every job card (Top picks, List, Board) = fit score (REQ-020) as one big number + title · company · place · age + one reasons line from the best résumé match (REQ-111): "<covered>/<required> skills · missing: <top 2>, +n". No sub-scores (Q-024). Match not computed yet → "Match pending". Saved/Applied cards add status (REQ-132).
Given best résumé covers 7 of 10, missing Go, Kubernetes · When card shown · Then "7/10 skills · missing: Go, Kubernetes".
### REQ-131 Setup checklist card on Today
Replaces the readiness card on Today; REQ-102 stays the data source, Profile Readiness tab unchanged. Top of Today only while a must-have is open: progress ring (done/total must-haves), one-line benefit ("Finish setup so CareerOS can fill applications for you."), one primary button: "Fill from résumé" when open items can come from the master résumé (Q-027), else the first open item's fix link. "Show all (n)" expands items. All must-haves done → card gone.
Given 2 of 5 must-haves done · When open Today · Then setup card first, ring 2/5, one primary button.
Given all must-haves done · When open Today · Then no setup card.
### REQ-132 Colour only for meaning; status = dot + word
Status everywhere (cards, rows, board, tabs) = dot + word, never colour alone. Colour only: amber = needs you, red = blocked / failed, green = Ready / Applied / Offer, and the word always names the stage ("Ready", "Applied · Interview", "Offer"); Applied-tab cards add a small stage progress line (Applied → Screening → Interview → Offer); everything else neutral. Cards carry a 3px left edge stripe in the status colour (neutral = no stripe). Contrast ≥4.5:1 both themes.
Given card "Needs you" · Then amber dot + word + amber stripe. Given card "Saved" · Then grey dot + word, no stripe.
