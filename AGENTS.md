# AGENTS.md

Guidance for Codex and other non-Claude agents. `CLAUDE.md` is canonical for project rules;
read it first, then `ARCHITECTURE.md`.

- Reviews: `$review <PR>` (`.agents/skills/review/SKILL.md`) follows `docs/CODE_REVIEW_PROMPT.md`.
- Setup: `python3 -m venv .venv && .venv/bin/pip install -e ".[test]" && .venv/bin/careeros init`.
- Tests: `.venv/bin/python -m pytest -q` (they use `examples/` only; no `profile/` or `config/` needed).
- Never commit `profile/`, `config/`, `CLAUDE.local.md`, `data/`, `.reviews/`, or anything with credentials.
