# Lessons

Evidence log: mistakes, corrections, discoveries. Not instructions; promoted rules live in CLAUDE.md /
AGENTS.md. Format and promotion rules: `~/.agent-learning/PROTOCOL.md`. Search before adding; bump
`Occurrences` on repeats.

## 2026-09-24 — Test silently depended on a gitignored file
Context: a test was passing locally but relied on data outside the committed repo.
What happened: the test silently depended on a gitignored file (personal/local data) instead of committed fixtures, so it could pass for one developer and fail (or lie) elsewhere, including CI.
Root cause: no rule required tests to read only repo-committed data.
Prevention: TDD (red-green-refactor); tests read only `examples/`, `tests/fixtures/`, and tmp — never `profile/`, `config/`, `data/` or `$HOME`.
Scope: repo
Occurrences: 1
Confidence: high
Status: promoted (CLAUDE.md#Testing (TDD))

## 2026-09-27 — Stacked/parallel UI PRs conflict on the committed bundle
Every PR that touches `ui/src` commits a rebuilt `src/careeros/ui/static/` with new content hashes, so two
open UI PRs always conflict there (rename/rename on every asset) and again in the UI snapshots.
Resolve by deleting the bundle and rebuilding, never by hand-merging: `git rm -rq --cached src/careeros/ui/static &&
rm -rf src/careeros/ui/static && (cd ui && npx -p node@22 -- npm run build)`; then
`CAREEROS_UPDATE_SNAPSHOTS=1 pytest tests/integration/test_ui_types_*` and inspect the snapshot diff.
Merge UI PRs one at a time and re-merge `main` into the next before its CI run.
