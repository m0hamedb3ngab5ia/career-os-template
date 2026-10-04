# Product docs — how to use

Repo uses `/product` (global skill, `~/.claude/skills/product/`). Works in Claude Code + Codex.

## Start (once per repo)
| repo | run | result |
|---|---|---|
| new / empty | `/product init` | creates this folder, then Discover questions → VISION |
| has code | `/product audit` | as-is diagrams, every found capability as proposed REQ, you triage keep/drop/change |
Run one, once. Folder exists after → never again.

## Day to day
| want | run |
|---|---|
| continue where left off (any chat, any agent) | `/product next` |
| new feature / big change / bug | `/product new "<what>"` → agent proposes lane Major/Feature/Fix, you confirm |
| answer pending questions | `/product questions` |
| change a requirement | `/product change REQ-014` (shows what it breaks, marks it needs-review) |
| independent test of a REQ | `/product verify REQ-014` |
| health check + refresh STATUS | `/product check` |
| ship / log what you observed | `/product release` · `/product learn` |
Plain prompts ("fix bug X") also work: CLAUDE.md/AGENTS.md block steers agent into system.

## Files (created only when stage runs)
| file | what |
|---|---|
| STATUS.md | read first: current stage, next step, gates, counts |
| OPEN_QUESTIONS.md | gaps agents need you to fill |
| VISION.md | user, problem, outcome, metrics |
| USER_REQUIREMENTS.md | **start here**: what users can do, plain words (USR). You own this. |
| REQUIREMENTS.md | technical REQ/NFR + Given/When/Then, derived from USRs by the agent |
| USE_CASES.md | UC + E2E specs + use-case diagram |
| SCOPE.md | MVP / must / should / later / excluded |
| IA.md · USER_FLOWS.md | navigation · FLOW steps, activity/state diagrams |
| DESIGN_SYSTEM.md | tokens, components, links to Claude Design mockups |
| ARCHITECTURE.md | components, data, APIs, threat model, diagrams (review before code) |
| DECISIONS.md | DEC entries; settled questions |
| TASKS.md · RELEASE.md | build tasks · releases + observations |
| trace.yaml | canonical status + links; `trace.py check` validates |

## Statuses
REQ: proposed → approved → in-progress → implemented → verified · also needs-review, rejected, deprecated.
You approve. Only `/product verify` sets verified.

## Gates (agent stops for you)
Major: Vision, Scope, Architecture, Release. Feature: one gate before build. Fix: none.
