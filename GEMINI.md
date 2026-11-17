# GEMINI.md

Guidance for Gemini CLI. `CLAUDE.md` is canonical for project rules: read it first (it says which
`ARCHITECTURE.md` sections to read), then `AGENTS.md` for setup and tests.

- Skills are Markdown files in `.claude/skills/<name>/SKILL.md`; to run one, read it and follow it for the job dir.
- Headless runs: `pipeline.yaml: llm.cli: gemini`; see `docs/GETTING_STARTED.md` "Using Codex or Gemini CLI".
- Never commit `profile/`, `config/`, `CLAUDE.local.md`, `data/`, `.reviews/`, or anything with credentials.
