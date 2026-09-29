# UI redesign — audit, IA, screens, batch builder, PR plan

Status: **proposal, awaiting approval**. No code changes here. Complements `docs/UI.md` (current spec); once a slice
lands, `docs/UI.md` is updated to match. Examples use fictional companies only.

Product questions every screen answers: **what is happening · what needs me · what do I do next · what can
automation handle**. System machinery (skills, CLI, files, run ids, check codes) stays one click down.

---

## 1. Audit (current state, `origin/main`)

### 1.1 Routes and responsibilities (`ui/src/app/routes.tsx`, nav in `ui/src/app/AppShell.tsx:25-42`)

| Route | Page | Does today | Data (API) |
|---|---|---|---|
| `/` | Today | stat tiles, "Needs you" (all open Action Items, sort/filter), pipeline chart, recent runs, next scheduled, paused banner | `/today`, `/status`, `/runs`, `/schedule` |
| `/pipeline` | Pipeline | Kanban, fixed board columns, drag = status change, filters tier/category/safety/location | `/pipeline`, `POST /jobs/{id}/status` |
| `/jobs` | Jobs | tracker-shaped table, tabs, Excel-style column filters in URL, search, export xlsx, open folder, inline edit | `/jobs`, `/jobs/tabs`, `/jobs/facets`, `/jobs/export` |
| `/jobs/:id` | Job detail | stepper + PipelineCard, Posting, Safety, Score, Documents, Contacts, Apply session, Activity (all equal-weight cards) | `/jobs/{id}`, `/jobs/{id}/pipeline` |
| `/actions` | Action Items | same open items as Today, grouped by heading, due, bulk done/reopen, add item, scam controls | `/actions*` |
| `/inbox[/:job]` | Inbox & Follow-ups | post-apply threads classified by inbox-sync, drafts | `/inbox*` |
| `/contacts` | Contacts | people per job, mark degree/mutuals | `/contacts*` |
| `/runs[/:id]` | Runs | start score/prepare batch (presets small…max/custom, dry run), current run, up next, history, schedule panel, catch-up, run log | `/runs*`, `/schedule*` |
| `/settings/:section?` | Settings | 10 schema sections from `settings_schema/sections.py` (General, Targets, Autonomy, Safety, Scout, Companies, Outreach, Notifications, Runs & schedule, + Storage) | `/settings*`, `/storage`, `/advise` |
| `/kit` | Kit | component gallery (dev) | — |

### 1.2 Duplicated concepts

| Concept | Where it appears | Problem |
|---|---|---|
| Open Action Items | Today "Needs you", `/actions`, Pipeline card badge, Job detail `review_reasons` ("Open action item: …") | same record, four renderings, no job grouping; Today groups by `Needs`, `/actions` by heading |
| Job status | Pipeline drag, Jobs inline edit, Job detail StatusMenu | fine (one API) but Pipeline is the only place that teaches the stages |
| "Run the next step" | Job detail PipelineCard (per job), Runs StartRunCard (batch), Today HeaderActions (prepare queue) | three entry points, three vocabularies ("Start", "Continue", "Approve & continue", "Run") |
| Paused state | Today PausedBanner, Runs PausedBanner + PauseAllControl | ok, shared component |
| QA result | DocumentsCard (fail_reasons, hard/soft counts), PipelineCard review_reasons ("QA check …") | two lists of the same failures |

### 1.3 Reusable kit (`ui/src/kit/*`) — keep

Button, Menu, Listbox, Popover, Dialog, Sheet, ConfirmPanel, Tabs, SegmentedControl, PillGroup, Switch, Meter,
chips (`StatusChip` etc.), EmptyState, FormField/inputs, Toast, ExternalLink, UnavailableButton, MarkDoneCircle,
`labels.ts` (code → label + tone). Missing: a **Details/disclosure** primitive, a **table with row selection**
(JobsTable has none), a **stat/count strip** that links somewhere (StatTiles is Today-specific).

### 1.4 Data models that shape the UI

- Status (`src/careeros/models.py:9`): `found scored skipped queued prepared needs_review applied screening
  interview offer rejected withdrawn ghosted`. Naturally splits into **automation funnel** (found→needs_review)
  and **recruiting lifecycle** (applied→offer + closed set).
- Action item types (`models.py:29`): `captcha review question salary bot_detection qa_fail send_linkedin
  send_email profile_gap laptop_required scam_suspected ghost_job other`, `needs` laptop/phone/anytime,
  priority H/M/L. Items carry `job_id` → groupable by job.
- Job pipeline state (`ui/services/job_pipeline.py`): stage, one next action, `blocked_reason`,
  `review_reasons: list[str]` (pre-formatted strings — the leak source, see 1.6).
- Runs (`runs/runner.py`, `service.py`): one global runner lock (one run at a time); per-job locks; stop
  reasons; retry bookkeeping (`Failures`); `run_batch(job_ids=…)` already accepts an explicit list.
- Ranking (`runs/ranking.py`): freshness, dream bonus, deadline bonus, fit (prepare only), retry bonus; returns
  `why` string per job. Selection = runner eligibility + scout prefilter.
- Auto-submit (`runs/policy.py:87-155`): off by default; Tier A never; safety must be `pass`; `manual` rules beat
  `allow` rules (`tier_*`, `fit_gte_n`, `dream`, `category_*`). Daily cap from `targets` volume (`policy.py:60`).

### 1.5 Terminology in the UI today

Mix of internal and human: "Queued/Prepared/Needs review", "Tier A/B/C", "Pass/Review/Block/Skip", "Profile gap",
"Laptop/Phone/Anytime", "High/Medium", "Other", "Runs", "dry run", "preset small/medium/large/max", "Approve &
continue", "Scout", "Catch up". Nav label "Inbox & Follow-ups", "Action Items".

### 1.6 Debug / system leaks (file:line)

| Where | Leak |
|---|---|
| `src/careeros/ui/services/job_pipeline.py:78-93` | review reasons built as `"QA: …"`, `"QA check {check}: {detail}"` (e.g. `keyword_coverage`), `"QA warning: …"`, `"Flag: …"`, `"Open action item: …"`; rendered raw at `ui/src/features/job-detail/PipelineCard.tsx:203` |
| `job_pipeline.py:63` | `"Apply session {outcome}: {reason}"` (raw outcome codes) |
| `src/careeros/runs/service.py:136-143` | Action Item text `"careeros run: /prepare-job failed … see \`careeros run show <id>\`"` → shown on Today/Action Items |
| `ui/src/features/job-detail/PipelineCard.tsx:31-40` | "Runs score-job headless: score.json, tier…", "per auto_submit" |
| `ui/src/features/job-detail/DocumentsCard.tsx:50-58,101-106` | "hard fails / soft fails", raw `fail_reasons` |
| `ui/src/features/pipeline/PipelinePage.tsx:169` | "writes `status.json` and the tracker" |
| `ui/src/features/runs/labels.ts:60` | "careeros doctor has FAIL lines." |
| `ui/src/features/runs/SchedulePanel.tsx:112` | "runs careeros tick every few minutes" |
| `ui/src/features/contacts/ContactsPage.tsx:133` | `careeros outreach mark` |
| `ui/src/features/settings/storage/StorageOverview.tsx:148` | `careeros storage --snapshot` |
| `ui/src/features/job-detail/HeaderActions.tsx:85`, `jobs/JobsPage.tsx:62` | tracker queue / CLI hint |
| error states in `PipelinePage.tsx:34`, `ActionItemsPage.tsx:60`, `ScamControls.tsx:15`, `InboxPage.tsx:67,138`, `SettingsPage.tsx:117`, `SaveBar.tsx:132`, `ContactsPage.tsx:142` | "Couldn't reach careeros ui" (ok-ish; say "Career OS isn't running") |
| `ui/src/kit/labels.ts:59` + `ACTION_TYPES` | "Profile gap", "Other", "Bot check" as type chips; types are nouns, not next steps |
| `ui/src/features/settings/format.ts:138`, `settings/types.ts:38` | section footers show `config/*.yaml` file paths |

### 1.7 Pipeline and mass-apply behaviour today

- Pipeline = Kanban of fixed columns (Found · Queued · Needs review · Applied · Screening·Interview · Offer + Closed
  line). Server caps cards per column and sorts by fit; drag sets status. With ~700 found jobs the Found column is a count plus 10 cards — unusable for selection.
- "Mass apply" does not exist. Batches exist only for **score** and **prepare** (`POST /runs`, budget presets,
  dry-run preview of the ranked selection, no per-job deselect). **Apply is per job only**
  (`service.py:115` raises without `job_ids`; `POST /jobs/{id}/pipeline`), never scheduled, Tier A staged.
- Scheduler (`careeros tick`) runs scout/score/prepare/prune only.

### 1.8 Responsive assumptions

Desktop sidebar layout + 390px phone companion (`docs/UI.md` "Screens"). Each feature CSS module has its own single
`max-width` breakpoint (no shared token); `pointer: coarse` tweaks in kit. Kanban relies on horizontal scroll at
phone width. Tables (Jobs) scroll horizontally on phone. No phone-specific navigation beyond the collapsed sidebar.

---

## 2. Information architecture

### 2.1 Navigation

| Group | Item | Route | Was |
|---|---|---|---|
| Primary | **Today** | `/` | Today + Action Items |
| Primary | **Jobs** | `/jobs` | Jobs |
| Primary | **Pipeline** | `/pipeline` | Pipeline (Kanban) + batch launching from Runs |
| Primary | **Inbox** | `/inbox` | Inbox & Follow-ups |
| Secondary | **Automation** | `/automation` (`/runs*` redirects) | Runs |
| Secondary | **Contacts** | `/contacts` | Contacts |
| Secondary | **Settings** | `/settings` | Settings |
| Hidden | All tasks | `/actions` (linked from Today) | Action Items nav item |
| Hidden | Run log | `/automation/runs/:id` | `/runs/:id` |

Challenge: keep the name **Pipeline** (not "Applications"). The page now owns both the automation funnel and the
recruiting lifecycle; "Applications" would only describe the second half. Nav counts: Today (items needing you),
Inbox (unread replies) only; drop the Jobs total (not actionable).

### 2.2 Page roles and relations

- **Jobs** = inventory. Every job, searchable/filterable, the only place with the full table. Selection starts here
  or in the batch builder; both produce the same batch.
- **Pipeline** = flow. Counts per stage, the batches moving jobs through the funnel, and the small set of live
  applications (applied → offer). A stage click opens **Jobs filtered** to that stage — no second job list.
- **Today** = what needs me now, grouped **by job**, plus what is coming (interviews, follow-ups) and what
  automation just did. It is the only home for open Action Items.
- **Inbox** = employer side after applying (replies, screening, follow-ups due).
- **Automation** = what runs by itself and when; manual runs and logs under Advanced.
- **Job detail** = one job's state and its single next action.

Action Items stop being a destination: they become the "Needs you" items of Today and the "Needs you" block on
Job detail. `/actions` stays (bulk done, add item, done list) as "All tasks", reachable from Today.

### 2.3 Advanced-only (behind `Details` / Advanced sections)

Run ids, run logs, stop-reason codes, budgets (max jobs/minutes), dry run, preset sizes, ranking weights, retry
counts, QA check codes and hard/soft counts, `apply_session` outcome codes, file paths (`config/*.yaml`,
`status.json`, job folders), CLI equivalents, port/host, debounce, pipeline column mapping, doctor output.

### 2.4 Term map (internal → human) — lives in `ui/src/kit/labels.ts`

| Internal | UI |
|---|---|
| found / scored | New / Scored |
| queued | Ready to prepare |
| prepared | Ready to apply |
| needs_review | Needs your review |
| skipped | Not a fit |
| Tier A | Top choice (always submitted by you) |
| Tier B / C | Good match / Stretch |
| safety pass/review/block | Company verified / Check company / Blocked |
| score run / prepare run / apply run | Score jobs / Prepare documents / Fill application |
| dry run | Preview |
| preset small/medium/large/max | 10 / 25 / 50 / all jobs |
| Runs | Automation |
| Action Item | task (in copy: "needs you") |
| Scout | Job discovery |
| tick / schedule | Automation schedule |
| catch-up | Missed runs |
| qa-review fail | Documents need review |
| QA `keyword_coverage` | "Resume misses N key skills from this role" |
| QA `numbers_consistent` / `employer_title_consistent` | "Resume and cover letter disagree on a detail" |
| QA `confidential_terms` | "A private term appeared in a document" |
| action `captcha` / `bot_detection` | "Solve a verification check" |
| action `question` / `salary` | "Answer N application questions" / "Decide a salary answer" |
| action `profile_gap` | "Add missing experience to your profile" |
| action `laptop_required` | "Finish on your laptop" |
| action `qa_fail` | "Review tailored resume" |
| action `scam_suspected` / `ghost_job` | "Check this company is real" / "Posting may be stale" |
| action `other` (run failed) | "Automation couldn't finish this job — retry or finish by hand" |
| stop `auth_required` / `usage_limit` | "Sign-in needed" / "Claude usage limit reached — resumes at …" |

Rule: backend keeps emitting codes; the UI maps them. Where the backend emits prose (review reasons, run-failure
Action Items) it moves to `{code, text, detail}` so the UI shows `text` and puts `detail` in Details.

---

## 3. Screen specs

Visual rules for all screens: one focal element per page; dividers and spacing before cards; no card-in-card;
color only for state/action; metadata shown only when it changes what the user does (drop Needs/priority chips
when every item is the same; show tier only for Top choice); contextual verbs on every button.

### Today
- **Goal**: what needs me now.
- **Hierarchy**: headline sentence ("3 jobs need you · 1 interview tomorrow") → Needs you → Upcoming → Automation.
- **Sections**: *Needs you* (grouped by job: company — role, "3 things need attention", sub-list of human tasks,
  one CTA per job from its pipeline state: Continue application / Review documents / Answer questions); *Upcoming
  interviews*; *Follow-ups due* (from Inbox); *Recent automation* (one line per batch/run: "Prepared 12 jobs ·
  2 need you"). Tasks without a job are a final "Other tasks" group.
- **Primary CTA**: the top job's CTA. **Secondary**: mark task done, snooze (due), View all tasks.
- **Removed**: stat tiles (become the headline sentence), pipeline chart (lives on Pipeline), sort/filter segmented
  controls (default order = blocked first, then priority, then due). **Moved**: next scheduled → Automation;
  paused banner stays (it blocks work).

### Jobs
- **Goal**: find and pick jobs.
- **Hierarchy**: search + saved tabs → filter chips with live count → table.
- **Sections**: existing tabs (`/api/jobs/tabs`) + column filters (unchanged URL format); row checkbox selection;
  sticky selection bar "12 selected · Add to batch · Change status · Export".
- **Primary CTA**: *Add N to batch* (opens Pipeline batch builder with the selection). **Secondary**: export,
  open folder, change status.
- **Removed**: subtitle about JobTracker.xlsx; Jobs count in nav. **Moved**: tracker sync / Excel queue notices →
  toast + Details.

### Pipeline
- **Goal**: see flow; launch and follow batches.
- **Hierarchy**: active batch (if any) → funnel strip → live applications.
- **Sections**:
  1. *Batches*: running/paused batch progress ("New grad SWE — Sep 28 · 25 selected · 12 submitted · 4 working ·
     3 need you · 6 waiting [Review 3] [Pause]"); "New batch" button; last 3 finished batches.
  2. *Automation funnel* (counts, not cards): New · Scored · Ready to prepare · Ready to apply · Needs your review ·
     Submitted-this-week. Each count links to `/jobs?f.status=…`.
  3. *Applications* (cards/list, small numbers): Applied · Screening · Interview · Offer, with Closed as a count
     link. Status change via menu (no drag).
- **Primary CTA**: *New batch* (or *Review N* when a batch has blocked jobs). **Secondary**: pause/resume, filters
  (tier/category/location) on the Applications section.
- **Removed**: Kanban drag, per-column card limits/"show all", `status.json` hint. **Moved**: StartRunCard (score/
  prepare budgets) → Automation › Advanced.

### Job detail
- **Goal**: this job's state and the one next action.
- **Hierarchy**: header (company, role, location, state sentence) → *Next step* block → *Needs you* list → supporting.
- **Next step block**: e.g. "Needs your review — 3 things need attention: Review tailored resume · Answer 4
  application questions · Sign-in needed [Continue application]". Uses `GET /jobs/{id}/pipeline` next action +
  grouped tasks for this job.
- **Supporting (below, dividers not cards)**: Documents (resume/cover/answers, QA summary in words), Company check
  (safety), Match (score), Posting, Contacts, Activity. Apply session screenshots under Documents › Application.
- **Primary CTA**: one, from pipeline state. **Secondary** (menu): change status, withdraw, override, open folder,
  re-run QA, force re-run.
- **Removed from default view**: stepper as a big section (becomes a thin progress line), QA codes/counts, run
  ids, per-stage "Runs X headless" help. **Moved** to *Details*: raw review reasons, `apply_session` outcome,
  evidence, file list, run links.

### Inbox
- **Goal**: employer replies and follow-ups.
- **Sections**: Needs reply · Follow-ups due · Updates (screening/interview/rejection) · Other.
- **Primary CTA** per thread: Reply / Send follow-up (draft, never auto-sent for LinkedIn). **Removed**: inbox-sync
  class codes in chips (human labels only). Nav label "Inbox".

### Automation (was Runs)
- **Goal**: what runs by itself, when, and did it work.
- **Hierarchy**: status line (On/Paused, next run time) → schedule rows → recent results → Advanced.
- **Sections**: rows "Job discovery · Every 4 h · Next 6:35 PM", "Scoring · Nightly", "Document prep · Nightly",
  "Inbox sync · Off", each with on/off + edit (links into Settings › Automation); missed-runs banner; recent results
  (human summaries). **Advanced** (collapsed): manual score/prepare run with size + preview, current run log,
  history table with run ids and stop reasons, scheduler install/uninstall, doctor output.
- **Primary CTA**: *Pause automation* / *Resume*. **Removed**: "uses your Claude Code subscription" subtitle →
  Details. Applications are not listed here (they are Pipeline batches).

### Settings
- **Primary sections**: Targets · Application preferences (answers, salary rules) · Resume defaults · Automation
  (schedule, volume/daily cap, auto-submit rules) · Safety · Companies · Notifications · Appearance.
- **Advanced / System** (one section, collapsed groups): Files, App (port/host, debounce), Claude, Pipeline column
  mapping, Ranking weights, Retry, Timeouts, Storage.
- Section footers stop showing `config/*.yaml` paths (move to Advanced › "Where this is saved"). Nothing deleted.

---

## 4. Batch builder (Pipeline › New batch)

### 4.1 Hard rules (not configurable, enforced in backend, shown in UI copy)

1. **Tier A is never submitted** by automation: filled and staged, lands in *Needs your review*.
2. **qa-review is never bypassed**: a job whose documents fail QA stops at *Needs your review*.
3. **LinkedIn is never automated**: LinkedIn-hosted applications are excluded from Fill/Submit stages and listed
   as "Apply yourself on LinkedIn" tasks.
4. **Apply is per job**: a batch is a **queue of per-job runs** (`run apply --job <id>` equivalents) executed one at
   a time under the existing global runner lock. No bulk apply code path.
5. Auto-submit happens only where `runs.auto_submit` already allows it (enabled + allow rules + safety pass +
   daily cap). A batch can only **narrow** that policy, never widen it.
6. Fill/Submit stages need Chrome + the user's session: such batches are **started by the user, never scheduled**.

### 4.2 Flow

| Step | Spec | Backed by |
|---|---|---|
| Setup | Name (default "Batch — Sep 28"), source: current Jobs selection or filters | new |
| Filters | Reuse Jobs filters (fit range, posted date, title, location, remote/hybrid, company, category, tier, ATS, status) + toggles: exclude applied, exclude duplicates/reposts, exclude blocked companies/keywords. **Live count** "127 jobs match" via `/api/jobs` count with the same URL filter params | `/jobs`, `/jobs/facets` (exists); salary/visa/experience filters only if the index has the column (gap G5) |
| Ranking | Highest match (fit desc) · Most recent · Best match + recency (existing `ranking.py` score, with its `why` as tooltip) · Oldest unprocessed · Random sample | `ranking.py` (exists for score/prepare); other modes = sort keys (gap G3) |
| Quantity | 10 / 25 / 50 / custom; shows "daily cap allows 18 submissions today" when stop point ≥ Submit | `policy.cap_status` (exists) |
| Selection | Exact list before start: checkbox per job, company · role · match % · posted · why ranked; "23 of 25 selected"; excluded jobs listed with reason (Top choice → staged, LinkedIn, blocked, already applied) | eligibility from `runner.eligibility` (exists) exposed per job (gap G2) |
| Stop point | Most prominent control, single segmented choice: **Score only · Prepare documents · Fill application, then ask me · Submit when allowed**. Last option disabled with reason when auto-submit is off in Settings | kinds score / prepare / apply (+ forced stage-only apply, gap G4) |
| Exceptions | Per type → default: CAPTCHA/bot check, sign-in, account creation, unexpected essay, salary, work authorization, missing answer → *send to Needs you, continue*; saved answer exists → use it (apply-job already reads `standard_answers.yaml`); company verification fail → *skip job*; QA fail → *Needs your review*; browser failure → retry once then Needs you; scam suspected, usage limit, auth for the whole tool → *pause batch* | apply-job already writes Action Items + `apply_session` outcomes; batch maps outcome → bucket (gap G1) |
| Confirm | Summary sentence: "Fill 23 applications, then ask you · auto-submit off · Top choice staged · filters: fit ≥ 75, posted ≤ 7 d" [Start batch]. Only confirm for Fill/Submit stages | — |
| Progress | Header counts: selected · done · working · need you · waiting · skipped; per-job table with human stage and reason; live via SSE `/events` | new batch status endpoint (G1) |
| Review queue | "Review 3" opens Today filtered to the batch's jobs (same grouped-by-job component) | Today grouping |
| Completed | Summary: submitted / staged for you / prepared / skipped (with reasons) / failed; "Retry 2 failed" | `Failures` retry state (exists) |
| Pause / cancel | Pause after current job (existing `/runs/pause` semantics); Cancel = stop queue, current job finishes its step; never leaves a half-submitted form (HANDS_OFF outcomes respected) | `/runs/pause`, `/runs/cancel` (exist, per run) |
| Retry | Per job or "retry failed"; respects `retry.max_attempts`; staged/submitted/blocked jobs never retried | `Failures`, `HANDS_OFF_OUTCOMES` (exist) |

### 4.3 Presets (challenge)

Brief proposes Conservative / Assisted / Autopilot presets **and** a stop point. They overlap: the stop point *is*
the policy, and submit rules already live in Settings › Safety/Automation. Proposal: **the four stop-point options
are the presets**, with a saved default in Settings; optional "Save these filters as…" named filter presets (stored
in `pipeline.yaml: ui.batch_presets`). "Autopilot" = "Submit when allowed" and inherits hard rules 4.1 — never
more.

### 4.4 Backend gaps (to build; flagged)

| # | Gap | Proposal |
|---|---|---|
| G1 | No batch entity or queue; one global run lock; apply refuses bulk | `data/runs/batches/<id>.json` (selection, stop point, per-job state) + a detached driver (`careeros batch run <id>`) that loops per job, calling `run_batch(kind, job_ids=[id])` per stage; batch status endpoint + SSE events |
| G2 | `POST /runs` takes no job list; no per-job eligibility preview | `POST /api/batches` with `{job_ids, stop_at, dry_run}` → per-job eligibility + reason |
| G3 | Ranking modes other than the runner score | sort keys on the jobs query (fit, posted, found_at asc, random with seed) |
| G4 | "Fill, then ask me" for non-Tier-A jobs needs a per-run auto-submit off switch | pass the existing `CAREEROS_AUTO_SUBMIT=0` env from the batch (already used for Tier A) |
| G5 | Salary, visa/sponsorship, experience level not indexed as filter columns | only if score/posting data has them; otherwise omit from v1 |
| G6 | Run-failure Action Items and review reasons are prose with CLI text | structured `{code, text, detail}` (see 2.4) |
| G7 | LinkedIn detection per job for exclusion | ATS/host field from posting (check `apply` module) → exclusion reason |
| G8 | "Scam suspected → pause batch" (4.2 Exceptions) is not mapped: no structured scam signal from an apply run | add a structured `scam_suspected` outcome (apply_session or run stop reason) and map it to *pause batch* |

---

## 5. PR slicing (template first, each ≤40 tool calls, TDD: vitest + pytest unit/integration)

Every PR that touches `ui/src` rebuilds `src/careeros/ui/static/` and refreshes `test_ui_types_*` snapshots
(`.agent/LESSONS.md` 2026-09-27); UI PRs merge one at a time, re-merging `main` before CI.

| # | PR | Files | New / reuse | API/data | Tests | Parallel |
|---|---|---|---|---|---|---|
| 1 | Foundations: term map + Details + visual tokens | `kit/labels.ts`, new `kit/Details.tsx`, `styles/tokens.css`, `global.css` | reuse labels tables | none | `labels.test.ts`, `Details.test.tsx` | first |
| 2 | Structured reasons (backend) | `ui/services/job_pipeline.py`, `runs/service.py` (action text), schema types | — | `review_reasons: [{code,text,detail}]`; action `what` human + `detail` | pytest unit (pure builders) + integration (`/jobs/{id}/pipeline`), snapshot | with 1 (no `ui/src` but schema.gen — merge after 1) |
| 3 | Nav regroup + Runs → Automation | `app/AppShell.tsx`, `routes.tsx` (redirects), `features/runs/RunsPage.tsx`, `SchedulePanel.tsx` | reuse SchedulePanel, StartRunCard inside Details | none | `AppShell.test`, `RunsPage.test` (Advanced collapsed, redirect) | after 1 |
| 4 | Today grouped by job | `features/today/*` (`actions.ts` `groupByJob`, `NeedsYou.tsx`, drop StatTiles/segments), link to `/actions` | reuse ActionRow, pipeline state for CTA | none (`/today`, `/inbox`) | `actions.test.ts` (grouping/order), `TodayPage.test` | after 2 |
| 5 | Job detail focal header | `features/job-detail/JobDetailPage.tsx`, new `NextStep.tsx`, `PipelineCard.tsx`, `DocumentsCard.tsx`, `actionHelp.ts` | reuse cards below, Details | uses 2 | `JobDetailPage.test`, `NextStep.test` | with 4 |
| 6 | Pipeline funnel + applications (no Kanban) | `features/pipeline/*`, `ui/services/pipeline.py` (funnel counts) | reuse StatusChooser, JobCard | `/pipeline` adds funnel counts | pytest unit (counts), vitest stage→`/jobs` link | after 3 |
| 7 | Batch backend A: model, preview, CLI | new `runs/batches.py`, `cli.py`, `ui/routers/batches.py` | `run_batch(job_ids)`, `eligibility`, `ranking` | `POST /api/batches` (dry_run), `GET /api/batches/{id}` | unit: selection, eligibility, **Tier A never submit, LinkedIn excluded, apply one job per run**; integration API | parallel with 3–6 (backend) |
| 8 | Batch backend B: driver, pause/cancel/retry, exceptions | `runs/batches.py`, `runs/service.py` hooks, events | `Failures`, `HANDS_OFF_OUTCOMES`, pause | SSE batch events | unit: outcome→bucket, pause/cancel, retry cap; integration: fake invoke end-to-end | after 7 |
| 9 | Batch builder UI (setup → confirm) | new `features/pipeline/batch/*` | reuse Jobs filters/`urlState.ts`, facets, SegmentedControl | uses 7 | vitest: live count, deselect, stop-point disabled reason, confirm copy | after 6+7 |
| 10 | Jobs row selection → Add to batch | `features/jobs/JobsTable.tsx`, `JobsPage.tsx` | selection handed via URL `ids=` | none | `JobsTable.test` (select all/page, bar) | after 9 |
| 11 | Batch progress + review queue | `features/pipeline/batch/Progress.tsx`, Today filter by batch | reuse Today grouping | uses 8 | vitest progress states | after 8+9 |
| 12 | Settings reorg + Advanced | `settings_schema/sections.py` (`advanced` flag), `features/settings/*` | reuse GroupCard | settings schema adds flag | pytest schema unit, `SettingsPage.test` | any time after 1 |
| 13 | Leak sweep (copy) | files in 1.6 not covered above (Contacts, Storage, error copy, Inbox labels) | labels | none | existing tests updated | last |

Out of scope: backend status model changes (statuses stay), new visual framework, removing any route.
