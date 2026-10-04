# Open questions

### Q-001 Who is the template for?
- Links: VISION User, NFR-005
- Default (recommended): owner first; template users = technical Mac users who self-serve via GETTING_STARTED. macOS-only stays.
- Status: open

### Q-002 Success metrics
- Links: VISION, REQ-092
- Default (recommended): applications/week, QA first-pass rate, interview rate by tier, candidate minutes per application.
- Status: open

### Q-003 Auto-submit: does Tier B/C actually auto-submit today?
- Links: REQ-033, REQ-046
- Evidence: README.md:44 says Tier B/C on GH/Lever/Ashby submit after QA; policy.py:25 `enabled: false` default, scheduled apply path not built (TODO.md:33), `apply fill` never submits.
- Default (recommended): assisted-only is the product today; README fixed to match; auto-submit stays a later opt-in.
- Status: answered
- Answer (2026-10-04): Auto-submit = additional opt-in mode to build, alongside assisted. Not the only method. README overstates today's behaviour → fix.

### Q-004 Half-built features: keep in scope?
- Links: REQ-038 Lever/Ashby/Workday adapters, REQ-063 inbox sync, REQ-046 scheduled apply, REQ-079 phone, REQ-092 weekly report
- Default (recommended): keep 038 + 063 (next), defer 046/079/092 to Later.
- Status: answered
- Answer (2026-10-04): Keep near-term: REQ-038 adapters, REQ-063 inbox sync, REQ-092 weekly report. Defer REQ-079 phone. REQ-046 in scope via Q-003.

### Q-005 Gmail auto-send
- Links: REQ-062
- Evidence: ARCHITECTURE.md:32 "Gmail auto-send after template confirmed" vs UI shows sending off; qa_ext checks `email_autosend_verified`.
- Default (recommended): drafts only for now; auto-send a later opt-in.
- Status: answered
- Answer (2026-10-04): Drafts only. Gmail auto-send rejected for now.

### Q-006 `/kit` component page shipped to users
- Links: REQ-078
- Default (recommended): keep but hide from nav (dev-only); cheap, aids UI work.
- Status: answered
- Answer (2026-10-04): Keep /kit, hide from nav (dev-only).

### Q-007 Prompt injection from posting text
- Links: ARCHITECTURE threat model, REQ-020..023
- Default (recommended): accept current `dontAsk` + allowedTools; add QA check later only if seen.
- Status: open

### Q-008 Action Items source of truth
- Links: REQ-052, REQ-073
- Evidence: TODO.md:52 move xlsx → data/action_items.json
- Default (recommended): approve the move as a requirement change (next Feature lane).
- Status: open

### Q-009 Résumé file types and size
- Links: REQ-093, REQ-101
- Default (recommended): PDF + DOCX, ≤5 MB; samples also txt/md.
- Answer (2026-10-04): default accepted.
- Status: answered

### Q-010 What does a comment on feedback do?
- Links: REQ-096, USR-002
- Default (recommended): AI re-drafts the suggestion using the comment; user then applies or dismisses. Alt: comment is just a note.
- Answer (2026-10-04): default accepted.
- Status: answered

### Q-011 Résumé types besides master
- Links: REQ-099, USR-003
- Default (recommended): `variant` (e.g. role-focused) and `other`; free-text name.
- Answer (2026-10-04): default accepted.
- Status: answered

### Q-012 How the master résumé feeds master.yaml
- Links: REQ-099, REQ-021
- Default (recommended): AI extracts bullets into a proposed master.yaml diff; user approves before write; numbers verbatim. Alt: auto-write.
- Answer (2026-10-04): default accepted.
- Status: answered

### Q-013 Readiness must-haves and what they block
- Links: REQ-102, REQ-103, USR-023
- Default (recommended): must = master résumé set, no example data, work-auth + salary answers, `claude` installed; nice = writing sample, credentials, EEO. Blocks apply only; score/prepare still run.
- Answer (2026-10-04): default accepted.
- Status: answered

### Q-014 Scoring unticked jobs
- Links: REQ-104, USR-024
- Default (recommended): score all scouted jobs (helps choose); prepare/apply only ticked. New jobs start unticked.
- Answer (2026-10-04): default accepted.
- Status: answered
