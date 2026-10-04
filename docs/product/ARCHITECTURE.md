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
