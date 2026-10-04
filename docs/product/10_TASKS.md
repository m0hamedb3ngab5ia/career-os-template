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

### TASK-014 Fill preview + ask unknown
Links: REQ-105 REQ-106 · Area: frontend · Done when: fill plan table edit + save-to-profile; needs_input prompt / Action Item; required unanswered blocks fill

### TASK-015 Jobs list: select, badges, check dialog
Links: REQ-104 REQ-109 REQ-114 REQ-115 · Area: frontend · Done when: checkbox + bulk select, injection badge + I checked it, Check a job dialog, résumé match table on job detail
