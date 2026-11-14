# chat-first

## Brief
- Goal: the product goes chat-first. The web UI shrinks to a read-only dashboard (Today + Jobs); everything else happens in Claude chat through skills and the `careeros` CLI.
- Why: the owner built a whole UI when most of it could live in chat; only the list of jobs in flight needs a stable view, because it gets lost in a long chat (DEC-024, `Reasoned by: human`).
- Acceptance: the UI offers only Today and Jobs; `docs/CHAT.md` maps every removed page to a command or skill; product trace marks each retired surface (`ui: retired-chat-first`) with its replacement and nothing is `verified` by this work; new skills `advice`, `today`, `interview-prep` and `score-job` `gaps[]` documented (REQ-139..142).
- Out of scope: removing the Python API (later pass); form filling stays on Playwright (`careeros apply plan` / `apply fill`); writing the new skills (sibling PR).

## Status
- State: active
- Branch/PR: `docs/chat-first` (docs); code and skills in sibling PRs
- Now: docs and product records updated (DEC-024, Q-032, CHAT.md)
- Next: remove now-unused API routers and their tests; decide fate of streams private-ui-redesign and ttv-user-test (both planned UI work that this supersedes)
- Waiting on user: Q-032 (is a trace annotation enough for retired surfaces?)
- Updated: 2026-11-14
