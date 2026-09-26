# career-os — UI design spec

Status: design. A mockup comes first; code (Phase 2) starts after the mockup is signed off.
Nothing in this file is built yet except where it says so.

## Goals

One local app that replaces opening the xlsx, reading `data/jobs/<id>/*.json` by hand and running CLI commands:

1. **See the pipeline live.** Every job's stage, from `found` to `offer`, with the pre-apply gates (safety verdict,
   QA, tier A review, "needs you") and the post-apply work (inbox classification, follow-ups, contacts).
2. **Act on what needs you.** Action Items as a to-do list; every item's `Link` is a real link.
3. **Run and watch the pipeline.** Scout, prepare, apply, inbox sync, with live progress.
4. **Change settings without editing YAML.** Every option is a form control; the app works on its own.
5. **Phone companion** for the things that don't need a laptop: approve drafts, mark items done, interview alerts.

Minimal, Apple Human Interface Guidelines look and behaviour (see [HIG notes](#hig-notes)).

## Data layer

**Decision: per-job JSON stays canonical; a SQLite index serves the UI; the xlsx stays as an export.**

| Store | Role | Written by |
|---|---|---|
| `data/jobs/<id>/*.json` (`status.json`, `score.json`, `safety.json`, `qa.json`, `apply_session.json`, `contacts.json`, `outreach.json`, …) | source of truth | skills + CLI, unchanged |
| `data/runs/` (`<run_id>/run.json`, `<run_id>/attempts/NNN.json` + `NNN.stream.jsonl`, `<run_id>/run.log`, `queue-<kind>.json`, `schedule.json`, `catch_up.json`, `pause.json`, `failures.json`, `storage.jsonl`, lock files) | source of truth for runs, the schedule, pause, catch-up and storage snapshots | `careeros run`, `careeros tick`, `careeros prune`, `careeros storage`; built |
| `data/careeros.db` (SQLite, WAL mode) | read index for the UI: jobs, status history, action items, contacts, runs | UI indexer only (rebuildable; delete it and it rebuilds); not built yet |
| `JobTracker.xlsx` | human-readable export, backup, and the place people already look | `careeros tracker sync`, unchanged |

Run history is already canonical in files (`data/runs/`, written atomically by `src/careeros/runs/store.py`), the
same pattern as the per-job JSON. The SQLite `runs` table is future UI work: the indexer reads `run.json` and the
attempt files; the UI never writes run records itself, it starts runs through the same code as `careeros run`.

Why:

- Skills and the CLI already write the JSON files. Moving the source of truth would mean rewriting every skill.
- The xlsx can't be queried, is slow to open for 1,000+ rows, and is locked while Excel has it open
  (writes go to `JobTracker.xlsx.pending.json`, see `tracker.py`). Fine for a human, poor for a live UI.
- SQLite is a file next to the data: no server, no credentials, one user, and fast filters/sorts/counts.
  **Not Postgres**: one candidate on one machine gains nothing from a database server and pays in setup and ops.
- The index is disposable. `careeros ui --reindex` rebuilds it from the files, so it can never drift for long.

Action Items and Contacts live only in the xlsx today. Phase 2 moves their source of truth into
`data/action_items.json` / per-job `contacts.json` (the xlsx tabs become an export like Jobs), so the UI never has to
write through an Excel lock. Until then, UI writes go through `Tracker` and inherit its lock + pending-queue handling.

UI writes always go through the existing APIs (`Store.set_status`, `Tracker.set_status`, `Tracker.mark_action_done`,
`careeros outreach mark`, …), then the indexer picks up the changed files. The UI never edits JSON directly.

## Live updates

A file watcher (`watchfiles`) on `data/jobs/**`, `data/runs/**`, `data/*.json|yaml` and the tracker path re-indexes the changed job
and pushes an event over **Server-Sent Events** (`/api/events`). The frontend patches its cache from the event.
No polling; works whether the change came from the UI, a terminal, a scheduled routine or a skill.

## Settings model

**Forms only.** Every setting is a switch, field or list that writes YAML directly. There is no "Ask Claude" box:
the UI has to stand on its own as an application, without a Claude Code session behind it.

- **Forms** for keys with a known shape, written back with `ruamel.yaml` round-trip mode so comments, key order and
  the example file's guidance survive. After each save the file is re-loaded with `Settings.load` (same
  `ConfigError` shape checks as the CLI); a failing save is rolled back and the error shown next to the field.
  - `targets.yaml`: candidate, location, categories, thresholds, `tiers` (auto_submit, cover_letter, outreach,
    review_required), `tier_rules` (ordered), `volume`, `safety` (auto_submit_ats, assisted_ats, pause_on, ghost
    thresholds, per-code `levels`), `scout` (sources, filters).
  - `companies.yaml`: dream_list, blocklist, company_domains, boards.
  - `pipeline.yaml`: paths, notify, outreach (`manual_if_connected`, `manual_if_mutuals`), and the Runs and Storage
    & efficiency groups below (`runs`, `schedule`, `llm.allowed_tools`, `retention`, `storage`, `advisor`).
  - `qa.yaml`: critic pass threshold, max regenerations, banned phrases.
- Profile, voice and templates are edited outside the UI for now (they are free text, not settings).
- Locked rows show policy that the system enforces and a form can't turn off: LinkedIn is draft-only; thank-you
  notes after interviews are always written by hand; Tier A is never auto-submitted; runs never apply.
- Every option shows its default with "(Recommended)" next to it, the same wording as the comments in
  `examples/config/pipeline.yaml`, and a "Reset to recommended" control per group.

### Settings › Runs

Writes `pipeline.yaml: runs`, `schedule` and `llm.allowed_tools`.

| Group | Controls (default) |
|---|---|
| Budget | preset picker: small (10 score / 2 prepare jobs, 30 min) · **medium (Recommended)** (25 / 5, 90 min) · large (50 / 10, 180 min) · max (150 / 25, 480 min) · custom (three number fields, `runs.custom`). A run stops at whichever limit comes first |
| Timeouts | per job: score 10 min (Recommended), prepare 45 min (Recommended); "Stop the run on a timeout" on (Recommended); stop after 3 failures in a row (Recommended) |
| Ranking weights | sliders with a live preview of the next 5 jobs and their "why": freshness 60, fresh for 48 h, stale at 30 days, dream bonus 25, deadline bonus 15 within 7 days, fit weight 0.5 (prepare only), retry bonus 30, each marked (Recommended) |
| Retry | attempts per job 2 (Recommended: retry once), then an Action Item on (Recommended) |
| Prepare | "Stop preparing at today's apply cap" on (Recommended); shows today's cap from `careeros run cap` |
| Auto-submit | shown **off and read-only**: "Runs never apply in this version". The `allow` / `manual` rule lists are visible (manual: Tier A, fit ≥ 85 (Recommended), with the fit threshold editable) so the policy can be reviewed before an apply path exists |
| Safety | "Run `careeros doctor` before every run" on (Recommended); required MCP servers for every run (empty (Recommended); the inbox sync job carries its own `gmail`); job lock expiry 120 min (Recommended) |
| Allowed tools | the `llm.allowed_tools` list as removable chips (the shipped list (Recommended)); a note that a tool missing here ends a run with "Tool not allowed", never a hang |
| Quiet hours | on, 09:00 to 18:00 (Recommended); applies to score, prepare and inbox sync (they use Claude); scout and prune ignore it. Time zone: local (Recommended) |
| Schedule jobs | one row per job with an enable switch and either an interval or times of day: scout every 3 h (Recommended: 2 to 3), inbox sync at 08:00 and 18:00 (off (Recommended) until the inbox-sync skill is finished; shows "needs Gmail login" when its MCP is not authenticated), score nightly at 01:00 (Recommended), prepare nightly at 02:00 (Recommended), prune weekly (Recommended); score and prepare rows take an optional preset override. Tick every 15 min (Recommended); missed after 60 min (Recommended) |
| Scheduler | Install / Uninstall buttons (`careeros schedule install`, `careeros schedule uninstall`) and the agent state from `careeros schedule status` (installed, loaded, last tick) |

### Settings › Storage & efficiency

Reads `careeros storage --json` and `careeros advise --json`; writes `pipeline.yaml: retention`, `storage`, `advisor`.

- **Breakdown chart**: one horizontal stacked bar of bytes by category (postings, résumés and PDFs, screenshots,
  run logs, tracker, other) with the disk's free space beside it. Below it, a small line chart of the
  `data/runs/storage.jsonl` snapshots (one per prune, plus any `careeros storage --snapshot`).
- **Projection**: projected size in 30 and 90 days against the storage budget, with the warning line at
  `storage.warn_at_pct`. Until `advisor.advise_after_days` of snapshots exist it says "Collecting data: N of 14
  days" instead of a projection.
- **Recommendations list**: one row per `careeros advise` recommendation: title, the evidence (e.g. "screenshots are
  61% of data/", "prepare runs average 38 of 45 min"), and the exact YAML change as a diff
  (`retention.screenshots_after_closed_days: 30 → 14`). Rows with a change have an **Apply** button that calls the
  same code as `careeros advise apply <id>` (comment-preserving write, validate, roll back on failure), then
  re-reads the list. Advice-only rows have no button. Nothing is ever applied without the click.
- **Settings** (each with its default):
  - Storage budget 1024 MB (Recommended); warn at 80% of it (Recommended); warn when disk free is under 10% (Recommended).
  - Advise after 14 days of snapshots (Recommended); suggest loosening retention after prune removed nothing for
    4 weeks (Recommended); run-efficiency advice after 5 runs of a kind (Recommended).
  - Retention: screenshots of closed jobs 30 days (Recommended), keep the confirmation screenshot on (Recommended),
    unprepared postings 90 days (Recommended), run logs 30 days (Recommended), run summaries 365 days (Recommended).
    0 turns a rule off.
  - A "Prune now" button with the dry-run list first (`careeros prune`, then `--yes` on confirm).

## Screens

Desktop 1440×900 (sidebar layout) plus a phone companion at 390×844. Light and dark.

1. **Today**: stat row (applied this week, open action items, upcoming interviews, auto-submit paused or not);
   "Needs you" list of open Action Items, priority H→L, grouped by `Needs` (laptop / phone / anytime), each with a
   clickable Link and a Done control; recent runs (with their stop-reason chip) and **next scheduled runs** (scout,
   score, prepare, prune with their next time from `careeros schedule status`, quiet hours shown as "after 6:00 PM").
   When `data/runs/catch_up.json` holds missed slots, a banner at the top: **"Missed runs — catch up?"** listing what
   was missed ("score: 3 slots since Tue 8:00 PM") with **Catch up** (`careeros run catch-up`) and **Dismiss**
   (`careeros run catch-up --dismiss`). Missed runs never start on their own; the banner is the only way in besides
   the CLI. While runs are paused the stat row shows "Runs paused until …" with Resume.
2. **Pipeline**: board with one column per stage: Found · Queued · Preparing · Needs review · Applied ·
   Screening / Interview · Offer · Closed (rejected, withdrawn, ghosted, skipped). Cards show company, role, fit,
   tier A/B/C, safety dot (pass / review / block / skip), QA state, override. Filters: tier, category, safety,
   location. Dragging a card sets status (both `status.json` and the tracker).
3. **Jobs**: the tracker's Jobs tab as a live table, same columns, inline Status / Override / Notes editing, saved
   views, search, Export xlsx, Open folder.
4. **Job detail**: header with status stepper; segments **Safety** (verdict, flags with code, level, detail,
   evidence links; Verify / Flag / Clear), **Score**, **Documents** (résumé PDF, cover letter, answers, QA critic
   scores), **Apply session** (step timeline with screenshots, outcome), **Contacts & outreach** (drafts, relationship
   badge), **Log** (log.md + status history). Toolbar: Prepare, Apply, Re-run QA, Set status, Override.
5. **Action Items**: all items grouped by due date (Overdue, Today, Tomorrow, Next 7 days, No date), soonest
   first, then priority; Open / Today / Done tabs; bulk done; Link always clickable. Any item that has a natural
   deadline shows it as secondary text under the task: relative wording when it's close ("Today, 6:00 PM",
   "Tomorrow", "In 3 days"), an absolute date further out, and the reason ("posting closes", "reply within 48
   hours", "saved form expires"). Red is only for overdue items and orange only for items due within 48 hours;
   everything else stays secondary grey. Undated items get an "Add date" control, never an invented deadline.
   Needs a new optional `due` (ISO datetime) and `due_reason` on `ActionItem` and a `Due` column on the Action
   Items sheet. The producers set them: inbox-sync (interview reply window, assessment deadline), apply-job
   (saved-form expiry), prepare-job (posting close date when the ATS gives one), and follow-ups (after-apply
   window).
6. **Inbox & follow-ups**: applied jobs with days since applying, last email, inbox-sync classification
   (rejection / assessment / interview / offer) and follow-up due dates; draft preview with Send / Edit / Skip.
   Auto-send only to a verified email; thank-you notes always manual.
7. **Contacts**: name, title, company, LinkedIn, email + confidence, draft, sent, replied. A **Connected** or
   **N mutuals** badge turns automation off for that person and shows "Tailor manually".
8. **Runs**: live and past runs of scout (per-source and per-filter counts), score and prepare batches
   (`careeros run`), apply-job (step stream + latest screenshot), inbox-sync; log pane; cancel. Sections:
   - **Now**: the running batch (from the runner lock and its `run.json`): kind, trigger (manual / schedule /
     catch-up), budget used ("7 of 25 jobs, 41 of 90 min"), the current job and its live stream-json events. Cancel
     sends SIGTERM; the batch stops before its next job with stop reason `cancelled`.
   - **Queue ("why next")**: the ranked jobs for the next score and prepare run, from `data/runs/queue-<kind>.json`
     (rewritten by every `careeros run score|prepare`, including `--dry-run`; `careeros run status` computes the live top 5 without writing it): rank, company, role, points, and the `why` text ("posted 20h ago (+60);
     dream company (+25)"). Excluded jobs (pruned, filtered, out of retries) sit in a collapsed "Not in queue" group
     with their reason.
   - **Run sheet** (Run score… / Run prepare…): a budget picker with presets small · **medium (Recommended)** ·
     large · max · custom (custom opens job and minute fields), each showing its jobs and minutes; a "Dry run first"
     toggle, on (Recommended), that shows the selection before anything calls Claude. Same code as `careeros run score|prepare
     --preset <p> [--max-jobs N] [--max-minutes M] [--dry-run]`. Prepare runs note "Never applies".
   - **Schedule panel**: next run time per job, last tick, LaunchAgent state, quiet hours; a link to
     Settings › Runs.
   - **Pause all**: a toolbar control with durations (1 hour, until tomorrow, until I resume (Recommended)); same as
     `careeros run pause --until +1h` / `careeros run resume`. The running batch stops before its next job; ticks
     skip due slots (not stored up).
   - **History**: past runs from `data/runs/<id>/run.json`: kind, trigger, ok/attempted, duration, and a
     stop-reason chip; a row opens the attempts (job, outcome, duration, session id, detail) and `run.log`.

   Stop-reason chips (label, then meaning). Neutral chips mean the run did its job; orange chips mean it needs you,
   and the chip carries the fix:

   | Stop reason | Chip | Means / fix |
   |---|---|---|
   | `completed` | Done | nothing left in the queue |
   | `budget_reached` | Job budget used | the preset's job count is done; the rest wait for the next run |
   | `time_budget` | Time budget used | the preset's minutes are spent (the job in flight is cut at the budget too) |
   | `daily_cap` | Daily cap reached | prepared jobs fill today's apply cap |
   | `paused` | Paused | stopped by Pause all |
   | `cancelled` | Cancelled | stopped by you (Cancel or Ctrl-C) |
   | `usage_limit` | Usage limit | subscription limit reached; retries at the next slot |
   | `auth_required` | Login needed | run `claude` and /login (or /mcp for a required MCP server) |
   | `permission_denied` | Tool not allowed | a skill needed a tool missing from `llm.allowed_tools` |
   | `timeout` | Job timed out | one skill call ran past its timeout; often a login or prompt wait |
   | `consecutive_failures` | Too many failures | 3 jobs failed in a row; open the attempts |
   | `doctor_failed` | Setup check failed | `careeros doctor` has FAIL lines |
   | `error` | Failed (orange) | a single-call run (inbox sync) failed for another reason, or a run crashed; open the attempt and `run.log` |

   A run whose process died without writing a stop reason shows **Interrupted** (grey).
9. **Settings**: grouped lists: General, Targets, Autonomy, Safety, Scout, Companies, Outreach, Notifications,
   Runs, Storage & efficiency (see [Settings model](#settings-model)).
10. **Phone: Today**: stat strip, phone/anytime Action Items, swipe to mark done, interview push banner.
11. **Phone: Approve draft**: cover letter or outreach draft with Approve / Edit / Reject.

Plus a **components sheet**: the 13 status chips, safety badges, tier chips, the 13 stop-reason chips, action-type glyphs, light/dark tokens.

## Running pipeline steps from the UI

Every run is a subprocess the server owns, one row in the `runs` table, and a stream of events on SSE.

- CLI steps (`careeros scout`, `careeros tracker sync`, `careeros safety check`): stdout lines stream to the log
  pane; the exit code sets the result (3 = block, 4 = skip for safety).
- Score and prepare batches: the server calls the same code as `careeros run score|prepare`
  (`careeros.runs.service.run_batch`), so ranking, budgets, locks, retry, the daily cap and every stop reason are
  identical to the CLI and the scheduler. The UI reads progress from `data/runs/<id>/` like any other file.
- Other skill steps (`/apply-job`, `/inbox-sync`, `/find-contacts`, `/draft-outreach`): run through
  `pipeline.yaml: llm.headless_cmd` + `llm.allowed_tools`. Every skill ends with a `RESULT: {json}` line (and
  sometimes `ACTION_ITEM`); the server parses it into the run record.
- Apply progress: `apply_session.json` is written step by step (`session.step()`), with screenshots under
  `screenshots/`. The watcher streams each new step to the Job detail and Runs screens.
- One run per job at a time (the per-job lock in `data/runs/locks/`, the same one `careeros job lock` takes) and one
  batch at a time (the global runner lock); the global volume caps (`targets.yaml: volume`) still apply. Cancel
  sends SIGTERM.
- Settings › Storage & efficiency's Apply button calls the same function as `careeros advise apply <id>`.

## Phase 2 implementation outline

- `careeros ui [--port 8765] [--host 127.0.0.1] [--reindex] [--no-open]` subcommand; server binds to `127.0.0.1` by
  default (any other `--host` requires auth; see Phone below).
- Optional extra in `pyproject.toml`: `ui = ["fastapi", "uvicorn", "watchfiles"]`, so the core CLI keeps its own
  dependencies. `ruamel.yaml` is already a core dependency (`careeros advise apply` writes config with it), so the
  UI's settings forms reuse that round-trip code instead of adding it.
- `src/careeros/ui/`: `app.py` (FastAPI routes + SSE), `index.py` (SQLite schema + indexer from `Store`),
  `runs.py` (starts `careeros.runs` batches and other steps, `RESULT:` parsing), `settings_io.py` (ruamel
  round-trip + validate + rollback, shared with `careeros advise apply`), `static/` (built frontend).
- Frontend: React + TypeScript, built to static files and served by FastAPI; no Node needed at runtime.
- Phone: the same app, responsive. The default bind stays `127.0.0.1`, so the phone path is a tunnel of the
  candidate's choice to that loopback port (e.g. an SSH tunnel or a private-network VPN such as Tailscale). An opt-in
  `careeros ui --host 0.0.0.0` LAN mode exists for home Wi-Fi, but it refuses to start without auth (a token set in
  config or generated and printed on first run, required on every request); no unauthenticated non-loopback bind.
- Tests (repo rule, tests first): unit tests for the indexer, settings round-trip (comments preserved, invalid
  values rolled back), `RESULT:` parsing; integration tests that start the app with a temp root and drive the API.
- Also needed before the Inbox & follow-ups screen is fully live: the follow-up scheduler (backlog P4).

## HIG notes

- System font stack (`-apple-system, BlinkMacSystemFont, "SF Pro Text"`), 8-point grid, large titles on top-level
  screens.
- Sidebar navigation with a translucent material; content in grouped inset lists (Settings) or plain tables.
- Semantic colours: accent blue; status colours differ in lightness as well as hue (pass / review / block are never
  told apart by colour alone: each has a glyph and a label).
- Sheets for edits and confirmations, not modal dialogs; destructive actions in red and always confirmed.
- Controls at least 44 px on phone; keyboard shortcuts on desktop (⌘K search, ⌘R run, space to preview).
- Follows the system light/dark setting.

## Accessibility and build checklist

The mockups were audited against the [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines).
Design-level fixes are in the mockup: focus and hover states, 44 pt phone targets, confirm or undo on destructive
actions, plain-language labels in place of raw codes, and real tables and headings. These items can only be met in
the React build:

- **Formatting:** dates, times and relative times through `Intl.DateTimeFormat` / `Intl.RelativeTimeFormat`, and
  numbers, percentages and sizes through `Intl.NumberFormat`. Hardcoded examples in the mockup ("Mon 16:40",
  "12 s ago", "1.8 MB / week") are placeholders. Render times on the client, or guard them against hydration mismatch.
- **URL state:** sort, filters, tabs, grouping, the selected Inbox thread, the Runs kind and budget, the Settings
  section and "Show as table" are kept in the query string, so views can be deep-linked and survive a reload.
- **Long lists:** virtualize Jobs (all), Pipeline › Found, the Runs history and the live run log.
- **Keyboard:** roving tabindex with arrow keys for tab lists, radio groups and segmented controls. Escape closes
  menus and sheets and returns focus to where it came from. On Save, focus moves to the first invalid field.
- **Forms:** controlled inputs have `onChange` (or use `defaultValue`). Unsaved Settings changes are guarded with
  `beforeunload` and a router guard. Buttons stay enabled until the request starts, then read "Saving…" or
  "Starting…".
- **Async feedback:** Mark done, Apply, Save and Send confirm through an `aria-live="polite"` toast with a 5–10 s
  undo window.
- **Platform:**
  - `touch-action: manipulation` and a deliberate `-webkit-tap-highlight-color` on phone.
  - `env(safe-area-inset-*)` padding.
  - A `<meta name="theme-color">` for each theme.
  - `color-scheme` set on `<html>`.
  - Sheets and toasts honour `prefers-reduced-motion`.
- **Screenshots:** apply-step images get `alt` text, explicit `width` and `height`, `loading="lazy"`, and a viewer
  that opens from the keyboard.
- **Review:** run the `web-design-guidelines` review on each UI PR.
