# Decisions

Stable design knowledge and intentional tradeoffs, so agents don't re-litigate them. Link to existing
docs instead of copying. Format: `~/.agent-learning/PROTOCOL.md`.

## Master profile as single source of truth
Decision: every résumé bullet, cover-letter claim, and form answer must trace to `profile/master.yaml`; fabrication is a hard fail.
Reason: keeps generated content truthful and auditable against one owned source.
Scope: repo
Relevant: ARCHITECTURE.md#Principles, CLAUDE.md (Hard rules)
Date: 2026-09-26

## Subscription-first LLM execution, no API key
Decision: all LLM work runs through the Claude Code subscription (skills in `.claude/skills/`, headless via `claude -p`); no Anthropic API key in the repo.
Reason: avoids per-token API billing and keeps LLM invocation auditable/scriptable via one interface.
Scope: repo
Relevant: ARCHITECTURE.md#Principles, ARCHITECTURE.md#Where the LLM runs
Date: 2026-09-26

## Autonomy tiers gate auto-submit
Decision: jobs are tiered A (dream firms, never auto-submit), B (strong fit, auto-submit after QA pass), C (volume, auto-submit, no cover letter unless required), with a per-job `Override` column.
Reason: bounds automation risk by how much the candidate cares about a given application.
Scope: repo
Relevant: ARCHITECTURE.md#Autonomy tiers
Date: 2026-09-26

## CI runs only in the public template
Decision: the GitHub Actions test workflow is skipped when `github.event.repository.private` is true; private-repo syncs are verified locally instead.
Reason: the private repo has a small Actions quota, so CI would exhaust it quickly.
Scope: repo
Relevant: .github/workflows/tests.yml
Date: 2026-09-26

## TDD required; tests never read private data
Decision: every code PR follows red-green-refactor with unit + integration tests, and tests may only read the repo itself (`examples/`, `tests/fixtures/`, tmp) — never `profile/`, `config/`, `data/` or `$HOME`.
Reason: keeps the test suite runnable in CI (which has no personal data) and prevents tests from silently depending on a developer's local, gitignored files.
Scope: repo
Relevant: CLAUDE.md (Testing (TDD))
Date: 2026-09-26

## Personal data lives outside the committed repo
Decision: `profile/`, `config/`, `data/`, `CLAUDE.local.md`, `.reviews/` are gitignored; `careeros init` populates them from `examples/` (a fictional candidate) or symlinks a private repo via `--link`.
Reason: lets the codebase be public and shareable while each user's personal job-search data stays local/private.
Scope: repo
Relevant: ARCHITECTURE.md#Principles, .gitignore, AGENTS.md
Date: 2026-09-25

## Built UI bundle is committed, not built at install time
Decision: `ui/` (TypeScript/npm) is built to `src/careeros/ui/static` and that output is committed and packaged (`tool.setuptools.package-data`); CI fails if the committed bundle doesn't match a fresh build.
Reason: lets `careeros ui` run for users without Node installed, while still catching a stale bundle in review.
Scope: repo
Relevant: pyproject.toml (package-data), .github/workflows/tests.yml (ui job: "Committed bundle is up to date")
Date: 2026-09-26
