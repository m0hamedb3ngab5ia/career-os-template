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
