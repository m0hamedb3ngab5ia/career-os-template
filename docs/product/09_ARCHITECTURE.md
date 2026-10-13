# Architecture — as-is (audit 2026-10-04)
Full detail: repo-root `ARCHITECTURE.md` (canonical design doc) + `docs/UI.md`. This file = product-level view + threat model only.

## Components
```mermaid
flowchart LR
  boards[ATS boards<br/>Greenhouse/Lever/Ashby] --> scout
  subgraph local[Candidate Mac, 127.0.0.1 only]
    tick[careeros tick<br/>LaunchAgent 15 min] --> scout & runner
    cli[careeros CLI] --> scout & runner & tracker & learn[learning] & creds[credentials]
    scout --> safety[safety: scam/ghost/registry] --> jobs[(data/jobs/&lt;id&gt;/*.json)]
    runner[runs: rank→lock→headless] -->|claude -p| skills[Claude skills<br/>score/tailor/letter/answer/qa/prepare/apply]
    skills --> jobs
    skills --> qa[qa.py + qa_ext] --> jobs
    skills -->|apply-job| chrome[Chrome / Playwright fill]
    jobs --> tracker[(JobTracker.xlsx)]
    ui[careeros ui FastAPI + React] --> idx[(SQLite index, disposable)]
    jobs & tracker & rundir[(data/runs)] -.watch+SSE.-> idx
    ui --> runner & tracker & learn
  end
  profile[(profile/ + config/<br/>gitignored or --link)] --> skills & qa & scout
  chrome --> atsforms[ATS application forms]
  skills -->|inbox-sync| gmail[Gmail MCP]
```
What to notice: files under `data/` are canonical; SQLite + xlsx are views. LLM only runs via `claude -p` one skill/job; Python owns ranking, budgets, locks, caps.

## Data model
```mermaid
erDiagram
  JOB ||--|| POSTING : "posting.json"
  JOB ||--o| SCORE : "score.json"
  JOB ||--o| SAFETY : "safety.json"
  JOB ||--o{ ARTIFACT : "resume/cover/answers"
  JOB ||--o{ QA_RESULT : "qa.json"
  JOB ||--o{ STATUS_EVENT : "status.json"
  JOB ||--o{ ACTION_ITEM : "xlsx Action Items"
  JOB ||--o{ CONTACT : "contacts.json"
  JOB ||--o| FILL_PLAN : "fill_plan/summary"
  JOB ||--o{ SUBMISSION : "submitted/<stamp>/manifest"
  RUN ||--o{ ATTEMPT : "attempts/NNN.json"
  ATTEMPT }o--|| JOB : "works on"
  BATCH ||--o{ JOB : "stop_at stage"
  PROFILE ||--o{ BULLET : "master.yaml ids"
  ARTIFACT }o--o{ BULLET : "cites by id"
  PROFILE ||--o{ STANDARD_ANSWER : "learned answers"
  PROFILE ||--o{ APPLY_LESSON : "hurdles"
```
What to notice: ARTIFACT→BULLET by id is the anti-fabrication contract. ACTION_ITEM still lives in the xlsx (move to JSON pending, TODO.md:52).

## AuthN / AuthZ
- UI binds 127.0.0.1 only; LAN deferred until auth + TLS (TODO.md:50). Host/CSRF checks: see `src/careeros/ui/security.py`.
- ATS creds: `~/.careeros/credentials.yaml` 0600 or macOS keychain; redacted from run logs.

## Threat model
| asset | boundary | surface | abuse | mitigation |
|---|---|---|---|---|
| Candidate PII (profile, answers) | public template repo | git push | personal data committed | gitignore, pre-push hook, CI PII guard |
| PII in forms | ATS / scam sites | apply-job | data harvesting | safety verdict, data minimization, sensitive labels never answered |
| Employer confidential terms | generated artifacts | résumé/letter/outreach | leak | QA `confidential_terms` hard fail |
| ATS passwords | run logs, repo | headless stream | leak | redactor, 0600, keychain, doctor warn |
| Local UI | browser on same host | HTTP/SSE | DNS rebinding / CSRF from other sites | loopback bind, host + origin checks |
| Candidate reputation | ATS / recruiters | auto-submit, outreach | wrong company / double submit / spam | QA wrong_company, submit-once, Tier A assisted, LinkedIn draft-only, daily cap |
| Prompt injection via posting text | LLM skills | posting description | skill misled into actions | `dontAsk` + allowedTools; (decision-needed Q-007) |

## Delta 2026-10-04 — profile, injection guard, résumé reuse, check a job
Scope: REQ-093..116, UC-001..012. Decisions: DECISIONS.md DEC-001..008. Nothing below exists yet.

### Components (new = bold)
```mermaid
flowchart LR
  ingest[scout / Check a job / import] --> store[Store.save_posting]
  store --> scan[**untrusted.scan**] --> flags[(**flags.json**<br/>selected, injection_*, below_threshold)]
  ui[UI Profile + Jobs] --> resumes[**resumes** store] --> rfiles[(profile/resumes/&lt;rid&gt;/)]
  resumes --> extract[**extract** pdf/docx/txt → text + ATS view]
  resumes -->|run kind review / resume_edit| runner[runs] -->|claude -p, no web| skills[review-resume / edit-resume / extract-master]
  runner -->|prepare: wrap untrusted| prep[prepare-job]
  match[**match** deterministic 0-100] --> resumes
  match --> score[(score.json skills)]
  runner --> pick[**resume pick**: reuse / tweak / tailor] --> match
  readiness[**readiness** = doctor + profile] --> gate{apply gate exit 7}
  gate --> apply[apply plan/fill, run apply, batch fill/submit, tick]
  qa[qa.py + **untrusted_content** check] --> prep
```
What to notice: one choke point each — `save_posting` scans every posting, `readiness` gates every apply path, `match` is the only scorer for résumé choice. LLM never decides reuse.

### Storage layout
| path | content | writer |
|---|---|---|
| `profile/resumes/<rid>/meta.json` | name, type `master\|variant\|other\|tailored`, category, versions `[{n, author user\|ai, source, at, below_threshold?}]` | `resumes.py` atomic |
| `profile/resumes/<rid>/v<n>/` | `original.<ext>` (uploads), `text.txt`, `ats.json`, `resume.json` (tailored/tweaked only, bullet ids) | `resumes.py` |
| `profile/resumes/<rid>/review.json` | state `running\|done\|failed`, run_id, items `{id, section, issue, suggestion, state, comments[]}` | review skill via CLI |
| `profile/master.proposed.yaml` | pending master.yaml diff (REQ-099); readiness open while present | extract-master; approve = ruamel write |
| `data/jobs/<id>/flags.json` | `selected`, `injection_suspected`, `injection_reasons[]`, `injection_cleared_at`, `below_threshold` | Store |
| `data/jobs/<id>/resume_choice.json` | per résumé `{rid, n, score, missing[]}`, chosen, action `reuse\|tweak\|tailor`, reason | `resume pick` |
Missing `flags.json` = legacy job → `selected: true` (REQ-104). New postings get `selected: false`.

### Data model delta
```mermaid
erDiagram
  RESUME ||--|{ VERSION : "v1..vN"
  RESUME ||--o| REVIEW : "review.json"
  REVIEW ||--o{ FEEDBACK : items
  FEEDBACK ||--o{ COMMENT : thread
  VERSION }o--o{ BULLET : "tailored/tweaked cite ids"
  JOB ||--o| FLAGS : "flags.json"
  JOB ||--o| RESUME_CHOICE : "resume_choice.json"
  RESUME_CHOICE }o--|| VERSION : chosen
  PROFILE ||--|| RESUME : "exactly one master"
```
What to notice: a job links to a résumé version instead of always owning a fresh one; tailored output becomes a `tailored` résumé reusable by later jobs.

### Sequences
UC-010 Check a job
```mermaid
sequenceDiagram
  actor U as User
  participant API as /api/jobs/check
  participant S as Store+scan
  participant R as runner (score)
  participant M as match
  U->>API: JD text or file (raw body, ≤5 MB)
  API->>S: extract → save_posting(source=manual) → scan
  alt injection hit
    S-->>U: flagged badge + Action Item (still scored)
  end
  API->>R: score-job --job X (no web tools)
  R-->>M: score.json required_skills
  M-->>U: per-résumé table, best vs threshold
  opt none ≥ threshold
    U->>R: Tailor from master (one run)
    R-->>M: rescore attempt
    M-->>U: ≥ threshold → use · else notice X/Y + missing → keep (below_threshold) / discard
  end
```
What to notice: scoring an injected posting is allowed (no tools that act); only prepare/apply wait for "I checked it".

UC-011 Prepare with reuse
```mermaid
sequenceDiagram
  participant Run as run prepare
  participant P as resume pick
  participant M as match
  participant Sk as prepare-job skill
  Run->>Run: eligibility: selected, not injection-blocked
  Run->>P: job X
  P->>M: score every résumé latest version
  alt best ≥ min_match
    P-->>Run: reuse rid/vN (no tailor)
  else tweak estimate ≥ min_match and gain ≥ min_tweak_gain
    P-->>Run: tweak base + ≤3 bullet ids
  else
    P-->>Run: tailor from master
  end
  Run->>Sk: prepare-job with resume_choice.json (posting in &lt;untrusted&gt;)
  Sk->>Sk: letter + answers (+ tweak/tailor only if asked) → qa
```
What to notice: the choice is Python, logged to `resume_choice.json` before any LLM call; the skill obeys it.

UC-012 Flag suspicious posting
```mermaid
sequenceDiagram
  participant Sc as scout/import
  participant S as Store.save_posting
  participant F as flags.json
  participant T as tracker Action Items
  participant Run as run prepare/apply
  Sc->>S: posting
  S->>S: scan text + raw html
  S->>F: injection_suspected + reasons
  S->>T: action add "check posting X"
  Run->>F: read → exit 2 "injection suspected"
  Note over F: UI "I checked it" → injection_cleared_at
```
What to notice: flag lives with the job, so CLI, UI and scheduler see the same block.

### FLOW-003 (UC-010) → 07_USER_FLOWS.md

### Contracts
| endpoint / CLI | in | out / errors |
|---|---|---|
| `GET /api/readiness` · `careeros doctor` | – | `{ready, items:[{id,label,must,done,fix_link}]}` |
| apply paths (REQ-103) | – | CLI exit 7 `not ready: <ids>`; API 409 `{code:"not_ready", items}` |
| `POST /api/jobs/check` | raw body + `?filename=` or JSON `{text}` | 201 `{job_id, flagged, run_id}`; 413 >5 MB; 415 type |
| `GET /api/jobs/{id}/matches` | – | `[{rid,name,n,score,missing[]}]` sorted, `threshold` |
| `PATCH /api/jobs/{id}/flags` · `POST /api/jobs/select` | `{selected}` / `{ids,selected}` · `{injection_cleared:true}` | 200 flags |
| `PUT /api/profile/resumes?filename=` | raw body | 201 `{rid, n:1, review_run}`; 413/415 |
| `GET/PATCH/DELETE /api/profile/resumes/{rid}[/versions/{n}]` | `{name,type}` | 409 deleting master / latest of master |
| `POST /api/profile/resumes/{rid}/review` · `.../feedback/{fid}/apply\|comment\|dismiss` | `{text}` for comment | 202 run_id; apply guard fail → 422 `{reason}` |
| `POST /api/profile/resumes/{rid}/master` · `GET/POST /api/profile/master-diff` | `{decision: approve\|reject}` | diff text |
| `PUT/DELETE /api/profile/samples` · `GET/PUT/DELETE /api/profile/answers/{key}` | raw body / answer | triggers learn-voice run |
| `careeros resume list\|add\|pick <job>\|match <job>` | – | JSON with `--json` |

### Failure + recovery
- `claude` missing/timeout in review → `review.json state: failed`, Retry reruns; upload kept.
- Extraction fails → version stored, `ats.json warnings: ["no text found"]`, match = 0.
- Crash mid-write → atomic tmp+replace everywhere (existing `runs/atomic.py`).
- Pending `master.proposed.yaml` → readiness must-have open → apply blocked, prepare not.

### Threat model delta (prompt injection)
| asset | boundary | surface | abuse | mitigation |
|---|---|---|---|---|
| Profile PII, résumé | posting text → LLM | posting/JD/email/import text in prompts | "send résumé to x@y", exfil via URL | `<untrusted>` wrapping + skill rule; per-kind tools (DEC-005); output guard `untrusted_content` |
| Apply actions | posting → apply-job | hidden instructions read in browser | wrong submit / extra fields | scan flag blocks apply until cleared; Tier A never auto; readiness gate |
| Candidate reputation | artifacts | injected text echoed in letter | "as an AI…" in letter | QA instruction-echo hard fail → regen once → Action Item |
| Local files | uploads | crafted PDF/DOCX (zip bomb, huge) | DoS / path traversal | 5 MB cap, docx read capped, rid server-generated, never user path |
| Scan itself | heuristic | paraphrased injection | missed flag | defence in depth: tools + guard still apply; scan only adds a human check |
Residual: WebSearch query strings in prepare can still carry data to a search provider (accepted, DEC-005).

### Quality scenarios
| NFR / REQ | scenario | test |
|---|---|---|
| REQ-111 determinism | same résumé+job twice → identical score + missing list | ACCEPT-111 |
| REQ-109 | recorded posting with zero-width + CSS-hidden text → flagged | E2E-012-01 |
| REQ-108 | fake skill prompt build: posting inside `<untrusted>`; score argv has no WebFetch | SEC-01 |
| REQ-110 | letter with unknown URL/email → `untrusted_content` hard fail | E2E-012-02 |
| REQ-103 | must-have open → every apply path exit 7 / 409 | ACCEPT-103 |

## Delta 2026-10-12 — résumé workspace (structured store, draft, history, annotations)
Scope: REQ-124..126, DEC-012. Decisions: DEC-013..019. Nothing below exists yet.

### Components (new = bold)
```mermaid
flowchart LR
  up[upload pdf/docx] --> extract[extract text, DEC-001] --> imp[**import run**: extract-master → resume.json + master proposal]
  imp --> guard{**verbatim guard**} -->|ok| ver[(v1 resume.json)]
  guard -->|fail| ai[Action Item, original kept]
  ws[**/resumes/&lt;rid&gt; workspace**] -->|autosave rev| draft[**draft API**] --> files[(draft.json + draft.changes.jsonl)]
  ws --> ann[**annotations API**] --> afile[(annotations.json)]
  runs[review / Apply-comment run] -->|proposals + replies only| ann
  ann -->|Accept: apply-edit base + fabrication guard| draft
  ws -->|Next/Done + idem key| pub[**publish**] --> ver2[(v&lt;n+1&gt;/ resume.json + changes.jsonl)]
  ver2 --> render[on demand: text, ATS, HTML, .tex; PDF cached for latest only, DEC-020]
```
What to notice: AI never writes the draft; only the user's Accept does, through the same guard as `apply-edit`. One schema, one import, one renderer.

### Storage layout (adds to 2026-10-04 table)
| path | content | writer |
|---|---|---|
| `profile/resumes/<rid>/draft.json` | working résumé JSON (DEC-018) + `rev`, `base_version` | draft API, atomic |
| `profile/resumes/<rid>/draft.changes.jsonl` | `{id, at, author, target_id, op, before, after, reverts?}` per line; reset on publish | draft API, append |
| `profile/resumes/<rid>/annotations.json` | `{id, kind, target_id, base, author, status, proposed, text, replies[], at}` | annotations API, runs via CLI |
| `profile/resumes/<rid>/v<n>/resume.json` | published, immutable; with `changes.jsonl` (authors, DEC-017) the only files per version; text/ATS/.tex/PDF rendered on demand (DEC-020) | publish |
| `profile/resumes/<rid>/cache/` | one PDF for the latest version, keyed by hash(resume.json) + renderer version; disposable | render |
| `profile/resumes/<rid>/import.json` | import state `running\|done\|failed`, run_id, guard failures | import run |

### Data model delta
```mermaid
erDiagram
  RESUME ||--|{ VERSION : "v1..vN immutable"
  RESUME ||--o| DRAFT : "draft.json"
  DRAFT ||--o{ CHANGE : "draft.changes.jsonl"
  RESUME ||--o{ ANNOTATION : "annotations.json"
  ANNOTATION ||--o{ REPLY : thread
  VERSION ||--|{ SECTION : "local ids"
  SECTION ||--|{ ENTRY : ""
  ENTRY ||--|{ BULLET : "source? = master.yaml id"
  ANNOTATION }o--|| BULLET : "target_id + base"
```

### Sequences
Edit + publish:
1. UI PUT draft `{rev, changes[]}` 500–800 ms after typing; server: rev ≠ current → 409; else apply, append changes, rev+1.
2. Revert change c: target value == c.after → append inverse; else 409 with both texts.
3. Accept suggestion s: target == s.base → fabrication guard → apply as change (author ai, accepted by user); else s → outdated.
4. Next/Done `{idem_key}`: seen key → return earlier result; hash(draft) == hash(latest) → no-op; else temp dir → rename `v<n+1>` → meta.json (+ master on onboarding) → move `draft.changes.jsonl` to `v<n+1>/changes.jsonl` → draft reset, open annotations re-checked (missing target → outdated).

### Failure + recovery
| failure | effect | recovery |
|---|---|---|
| crash mid-publish | temp dir left, meta.json unchanged | startup removes stale temp dirs; draft still there |
| tab closed before debounce | flush on `pagehide` (sendBeacon) | last ≤800 ms may be lost only on hard kill |
| import guard fails | no JSON, `import.json` failed | Action Item; user retries or edits; original v1 kept |
| two tabs | second save 409 | UI reloads draft, re-applies local undo stack where targets match |

### Quality scenarios (invariants, DEC-017)
| invariant | scenario | test |
|---|---|---|
| no lost edits | stale rev save → 409, draft unchanged | unit draft API |
| no silent AI changes | review run output touches only annotations.json | integration run fixture |
| no duplicate versions | double Next with same key / unchanged draft → one version | unit publish |
| deterministic render | same JSON twice → identical text, ATS and `.tex` (on-demand output must be stable) | integration render (skipif no LaTeX) |
| auditable revert | revert appends inverse; conflicting revert refused | unit history |
| import never invents | bullet not in text.txt → import failed | unit guard |

## Delta 2026-10-13 — Jobs on Today, tracker in Jobs (DEC-022)
Scope: REQ-127..132, UC-015, UC-016, FLOW-004, FLOW-005. Today = read-only summary; Jobs = the workspace. No new store, no new job state.

### Components (changed = bold)
```mermaid
flowchart LR
  ix[(SQLite index, rebuilt)] --> bucket[**services/jobs.py TABS + _tab_clause**: recommended / saved / applied]
  bucket --> list[GET /api/jobs?tab=] --> jobsui[**Jobs: tabs + List / Table / Board**]
  bucket --> tabs[GET /api/jobs/tabs counts] --> jobsui
  bucket --> today[**GET /api/today top_picks** = first N of recommended] --> todayui[**Today: Top picks / setup card**]
  list --> reasons[**match.matches for rows on the page only**, résumé texts loaded once per request]
  jobsui -->|Board drag| status[POST /api/jobs/id/status → Tracker.set_status, atomic, NFR-002]
  todayui -->|click| jobsui
  old[/pipeline] -->|**redirect**| jobsui
```
What to notice: Today and the Jobs counts call the same bucket clause, so a job can never be "recommended" on one page and not the other.

### Buckets (replace the current TABS: active / review / applied / tier_a / all)
| tab | clause | notes |
|---|---|---|
| recommended | fit scored, `selected = 0`, status not skipped, not in APPLIED_STATUSES, not closed | sort fit desc; Today takes the first N |
| saved | `selected = 1`, not in APPLIED_STATUSES | Start pipeline lives here (FLOW-004) |
| applied | status in APPLIED_STATUSES | Board view: one column per status |
Old tab keys in a saved URL → map to the nearest new tab (review/tier_a/all → recommended with that filter), never a 400.

### Reasons line (REQ-130)
- Computed on read: `match.matches()` is deterministic, no LLM, and its inputs (résumés) change after scoring, so a stored value goes stale.
- Only the rows returned (one page of List, N Top picks); résumé texts read once per request, not once per row.
- `ponytail:` no cache. Add one keyed on (job score.json mtime, résumé version ids) only if a timed request on a ~750-job copy is slow.

### Settings
- `ui.jobs_view` (list / table / board) in `data/ui_state.json` via existing `GET/PUT /api/ui-state` (atomic write, same as `tour_done`).
- `/pipeline` route: 308 to `/jobs?tab=applied&view=board`; `GET /api/pipeline` kept until the Board reads from `/api/jobs?tab=applied`, then removed.

### Failure + recovery
| failure | effect | recovery |
|---|---|---|
| Board drag while Excel holds the tracker | write queued to `.pending.json` | card shows "Saved, Excel open"; `careeros tracker flush` |
| status write refused (`acts.set_status` raises) | card snaps back | refusal reason shown inline |
| résumé file unreadable during reasons | that row has no reasons line | row still listed; no 500 |

### Quality scenarios
| invariant | scenario | test |
|---|---|---|
| one bucket rule | Today top picks ⊆ recommended tab rows, same order | unit services |
| counts match lists | tab count == rows returned without limit | unit services |
| no duplicate state | Board drag changes only the tracker status | integration API |
| reasons cost bounded | reasons computed for page rows only (call count) | unit with fake match |
