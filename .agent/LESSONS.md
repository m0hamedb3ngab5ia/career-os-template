# Lessons

Evidence log: mistakes, corrections, discoveries. Not instructions; promoted rules live in CLAUDE.md /
AGENTS.md. Format and promotion rules: `~/.agent-learning/PROTOCOL.md`. Search before adding; bump
`Occurrences` on repeats. How to use: `~/.agent-learning/README.md`.

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
Context: two open PRs that both touch `ui/src`.
What happened: each PR commits a rebuilt `src/careeros/ui/static/` with new content hashes, so they conflict on every asset (rename/rename) and again in the UI snapshots. Repeat 2026-09-29 with parallel UI PRs.
Root cause: built bundle is committed and content-hashed.
Prevention: never hand-merge the bundle: `git checkout origin/main -- src/careeros/ui/static`, rebuild (`cd ui && npx -p node@22 -- npm run build`), then `CAREEROS_UPDATE_SNAPSHOTS=1 pytest tests/integration/test_ui_types_*` and inspect the diff. Merge UI PRs one at a time.
Scope: repo
Occurrences: 2
Confidence: high
Status: promoted (CLAUDE.md#Git / PR workflow)

## 2026-09-28 — Headless run denied a chained Bash call
Context: `careeros run apply` launches skills with `claude -p --permission-mode dontAsk --allowedTools ...`.
What happened: the apply-job agent ran `careeros doctor --quiet; echo "doctor=$?"; ...`; `echo` is not allowlisted, so the whole call was denied, the skill stopped with RESULT status `unchanged`, and the run showed "completed, 1 job(s) done" with nothing applied.
Root cause: skills didn't forbid chaining; classify ranked invalid_result over the denial; completed detail hid failures.
Prevention: skills say "one command per Bash call" (contract test); a denial behind an invalid RESULT is `permission_denied`.
Scope: repo
Occurrences: 1
Confidence: high
Status: mechanized (tests/test_skill_contracts.py)

## 2026-09-29 — Worktree tests imported another checkout's code
Context: template worktrees share one `.venv`, an editable install of a different checkout's `src/`.
What happened: pytest and openapi regen in a worktree ran the other checkout's code, so results and generated files were wrong.
Root cause: the editable install wins over the worktree's `src/`.
Prevention: run `PYTHONPATH=src python -m pytest ...` and `PYTHONPATH=src` for openapi regen in every worktree.
Scope: repo
Occurrences: 1
Confidence: high
Status: promoted (CLAUDE.md#Gotchas)

## 2026-09-29 — `gh pr merge --admin` refused
Context: merging own template PRs.
What happened: branch protection enforces admins, so `gh pr merge --admin` is refused and cannot skip the check.
Root cause: protection applies to admins too.
Prevention: wait for the `pytest` check, then `gh pr merge --squash` (or `--auto`).
Scope: repo
Occurrences: 1
Confidence: high
Status: promoted (CLAUDE.md#Git / PR workflow)

- 2026-10-12 Overwrote an existing handoff: picked NN from the stale main checkout, wrote with `cat >` in a fresh origin/main worktree. Rule: compute handoff NN by `ls handoffs/` inside the worktree you write in; create with `set -o noclobber` (`>`) so an existing file errors.

- 2026-11-15 Code prefilters that skip jobs before Claude scores them (user worry: they get it wrong). Rule: when in doubt, never skip (a wrong skip loses a job; a wrong pass costs one Claude call). Location checks decide by parsed US state (region names like "Northeast US" in config expand to states; a posting saying only "Northeast"/"East Coast", a city with no state, "Multiple locations" or "US" → don't skip); multi-location skips only if every location fails; remote/hybrid never skipped on location; missing pay never a skip reason alone; skip notes start "prefilter:" with the parsed values. Before enabling or changing a prefilter, compare it against existing Claude score.json decisions: any job Claude chose "prepare" that the prefilter skips is a bug, ship only at 0. Pass these rules to any agent building or changing a prefilter.

- 2026-11-15 `careeros run score --force --job X` silently skips a job whose status is `skipped` ("status skipped; not started", exit 0). To rescore: `careeros job status X found --note "rescore: <why>"` first, then dry-run to confirm it is a candidate (the run's age filter still applies).
