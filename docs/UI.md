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
| `data/careeros.db` (SQLite, WAL mode) | read index for the UI: jobs, status history, action items, contacts, runs | UI indexer only (rebuildable; delete it and it rebuilds) |
| `JobTracker.xlsx` | human-readable export, backup, and the place people already look | `careeros tracker sync`, unchanged |

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

A file watcher (`watchfiles`) on `data/jobs/**`, `data/*.json|yaml` and the tracker path re-indexes the changed job
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
  - `pipeline.yaml`: paths, schedule, notify, outreach (`manual_if_connected`, `manual_if_mutuals`).
  - `qa.yaml`: critic pass threshold, max regenerations, banned phrases.
- Profile, voice and templates are edited outside the UI for now (they are free text, not settings).
- Locked rows show policy that the system enforces and a form can't turn off: LinkedIn is draft-only; thank-you
  notes after interviews are always written by hand.

## Screens

Desktop 1440×900 (sidebar layout) plus a phone companion at 390×844. Light and dark.

1. **Today**: stat row (applied this week, open action items, upcoming interviews, auto-submit paused or not);
   "Needs you" list of open Action Items, priority H→L, grouped by `Needs` (laptop / phone / anytime), each with a
   clickable Link and a Done control; recent runs and next scheduled runs.
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
8. **Runs**: live and past runs of scout (per-source and per-filter counts), prepare-job (score → tailor → cover
   letter → QA), apply-job (step stream + latest screenshot), inbox-sync; run buttons with options; log pane; cancel.
9. **Settings**: grouped lists: General, Targets, Autonomy, Safety, Scout, Companies, Outreach, Notifications,
   Schedule (see [Settings model](#settings-model)).
10. **Phone: Today**: stat strip, phone/anytime Action Items, swipe to mark done, interview push banner.
11. **Phone: Approve draft**: cover letter or outreach draft with Approve / Edit / Reject.

Plus a **components sheet**: the 13 status chips, safety badges, tier chips, action-type glyphs, light/dark tokens.

## Running pipeline steps from the UI

Every run is a subprocess the server owns, one row in the `runs` table, and a stream of events on SSE.

- CLI steps (`careeros scout`, `careeros tracker sync`, `careeros safety check`): stdout lines stream to the log
  pane; the exit code sets the result (3 = block, 4 = skip for safety).
- Skill steps (`/prepare-job`, `/apply-job`, `/inbox-sync`, `/find-contacts`, `/draft-outreach`): run through
  `pipeline.yaml: llm.headless_cmd`. Every skill ends with a `RESULT: {json}` line (and sometimes `ACTION_ITEM`);
  the server parses it into the run record.
- Apply progress: `apply_session.json` is written step by step (`session.step()`), with screenshots under
  `screenshots/`. The watcher streams each new step to the Job detail and Runs screens.
- One run per job at a time; the global volume caps (`targets.yaml: volume`) still apply. Cancel sends SIGTERM.

## Phase 2 implementation outline

- `careeros ui [--port 8765] [--host 127.0.0.1] [--reindex] [--no-open]` subcommand; server binds to `127.0.0.1` by
  default (any other `--host` requires auth; see Phone below).
- Optional extra in `pyproject.toml`: `ui = ["fastapi", "uvicorn", "ruamel.yaml", "watchfiles"]`, so the core CLI
  keeps its four dependencies.
- `src/careeros/ui/`: `app.py` (FastAPI routes + SSE), `index.py` (SQLite schema + indexer from `Store`),
  `runs.py` (subprocess runner, `RESULT:` parsing), `settings_io.py` (ruamel round-trip + validate + rollback),
  `static/` (built frontend).
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
