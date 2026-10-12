# TODO

Generic build backlog. Personal inputs (profile bullets, voice samples, dream list, board slugs)
belong in each candidate's own private repo, not here. Completed items: `docs/TODO_DONE.md` (verbatim detail, cold).

## System — build backlog
Done (detail in `docs/TODO_DONE.md`): P0 config/profile/init · P1 scout + tracker · P2 skills · P2.5 QA confidential-terms check · outreach relationship gate · unattended runs (`run score|prepare`, locks, daily cap) · scheduler (`tick`, LaunchAgent) · `storage`/`advise` · SQLite run index · `careeros ui` server slice 1 · `doctor`.
- [ ] P3 applier: Chrome adapters greenhouse → lever → ashby; bot-detection heuristics; screenshot on every submit
- [ ] P4 inbox-sync (Gmail MCP) + push notify + follow-up drafts
- [ ] Gmail label for job mail: inbox-sync applies a `Career OS` label (config `inbox.label`) and archives application confirmations/rejections after updating the tracker, so the inbox is not spammed; a Gmail filter suggestion in docs/GETTING_STARTED.md
- [ ] P5 find-contacts + draft-outreach (LinkedIn URL, email guess w/ verification, message)
- [ ] P6 custom scrapers for `ats: custom` boards (company career pages without a public ATS API)
- [ ] P7 LinkedIn Jobs discovery (never Easy Apply)
- [ ] Workday adapter (assisted mode)
- [ ] Move Action Items source of truth from the xlsx to data/action_items.json (+ due/due_reason); the UI writes
      through Tracker until then (docs/UI.md)
- [ ] Action Item due dates from the producers: inbox-sync (interview reply window, assessment deadline), apply-job
      (saved-form expiry), prepare-job (posting close date), follow-ups (after-apply window). `ActionItem.due` /
      `due_reason`, the tracker's Due columns and the UI's "Add date" exist; nothing sets them automatically yet
- [ ] Scheduled apply path: honour `runs.auto_submit.enabled`, gated by the daily cap (`careeros run cap --check`)
      and `auto_submit_decision` (Tier A and non-pass safety always manual); off by default
- [ ] Finish the inbox-sync skill, then set `schedule.jobs.inbox_sync.enabled: true` (the job, 08:00 + 18:00 with a
      Gmail MCP auth preflight, is already in the scheduler). Follow-ups in the scheduler: still to do
- [ ] `/schedule` cloud routines as an alternative to the LaunchAgent (runs while the Mac is off; needs the repo and
      data reachable from the cloud session) for scout + inbox-sync
- [ ] Weekly self-review report: acceptance rate by category/tier, QA fail reasons, time saved
- [ ] P1.5 scout source: Simplify New-Grad GitHub list parser (public, ATS links)
- [ ] P7 chrome discovery: Jobright + Handshake feeds (saved-search URLs → `config/companies.yaml: searches`)

## UI — backlog (after the UI build, PRs #34–#59)
- [ ] Phone layout: make the UI usable at phone width (deferred)
- [ ] LAN mode: deferred; needs real auth (token/pairing) and TLS before binding beyond loopback
- [ ] Live end-to-end pass of the UI against a real candidate's data (deferred)
- [ ] Runs page: scout/tracker/prune runs never show under "Now" (`RunControl.current()` only reads runner.lock)
- [ ] Watcher: nested screenshot dirs; tracker dir missing when the watcher starts
- [ ] Template sync guard: `pull` lets untracked files through; refs planted with `git fetch <url> x:refs/remotes/template/x`
      or `update-ref` bypass the ls-remote check (full fix: exclude only the remote sha + `git ls-remote template` heads)
- [ ] Verify then fix: `undo_mark_safe` needs an exact company-name match (`ui/services/actions.py`); a companies.yaml
      change emits two SSE `changed` events (`ui/reindex.py`)
- [ ] Runner: a raising finalize hook masks the original error (no test that the lock is still released);
      `rs.save_run`/`rs.log` raising in an outer `finally` leaves the lock held; `run_skill` records done when invoke raises
- [ ] Remove unused old sheet styles in `ui/src/kit/overlay.module.css`
- [ ] Action Items: move the source of truth off the xlsx (see System backlog) so the UI stops writing through Tracker

## Future (not now)
Done: web UI dashboard = `careeros ui` (PRs #34–#59, spec `docs/UI.md`).
- [ ] Action Items redesign: group by `Type` + `Needs` column = `laptop` (Chrome/Handshake/Workday session, candidate present) | `phone` (approve/send from anywhere) | `anytime`; sort by Priority then NextActionDate; separate "Today" view. Tier A submits, Handshake, Workday review pages = `laptop`. LinkedIn sends, email approvals, cover-letter reviews = `phone`.
- [ ] Handshake apply sessions: candidate logged in + present; system drives Chrome, candidate debugs live. Assisted mode only.
- [ ] Action Items tab: answer box on question/salary items that calls `POST /actions/{id}/answer` (learns the answer, closes the item); lessons list/add UI on top of `GET|POST /learning/lessons`. Backend shipped with `careeros learn`.
- [ ] Phone access: approve/reject drafts, mark actions done, get interview alerts. Candidates: Google Sheet mirror of tracker, push notifications (already planned), Claude Code remote sessions, or the web UI made mobile-first.

## Ghost jobs
Done: ghost thresholds + reposted/aggregator/freeze rules in `src/careeros/safety/ghost.py`, `data/posting_history.json`, `careeros safety signal` (verbatim rules: `docs/TODO_DONE.md`).
- [ ] Tracker `PostedDate` column (needs a Jobs-sheet column migration like Action Items `Needs`).

## Safety — scam / data-harvesting protection
All items done. Verdicts Pass/Review/Block with reason codes (`careeros safety check|fields`, `src/careeros/safety/scam.py`, levels in `targets.yaml: safety.levels`); hard-stop list, allowlist, data minimization, flagged registry: verbatim in `docs/TODO_DONE.md`. Hard stops never auto-submit (→ Action Item).
