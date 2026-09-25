---
description: Dual review (Claude + Codex) of a PR against its base branch
argument-hint: <PR number> [--post]
---

Review GitHub PR `$ARGUMENTS` with two independent reviewers, Claude (you) and Codex, then merge
their findings. Method, invariants and output format: `docs/CODE_REVIEW_PROMPT.md`.

1. Parse `$ARGUMENTS`: first token = PR number (if missing, ask and stop); `--post` = also post the
   merged findings as a PR comment.
2. Load metadata: `gh pr view <PR> --json number,title,body,baseRefName,headRefName,url`.
   Base is the PR's `baseRefName` (PRs here are often stacked; do not assume `main`).
3. **Start Codex first, in the background:** run `scripts/review.sh <PR>` with Bash
   `run_in_background: true`. It fetches the PR into an isolated worktree at
   `.reviews/pr-<PR>/wt`, runs `codex exec` read-only with the same prompt, and writes
   `.reviews/pr-<PR>/codex.md`. Do not wait on it yet.
4. **Your review, in parallel:** work inside `.reviews/pr-<PR>/wt` once the script has created it
   (or `git fetch origin pull/<PR>/head:refs/pr/<PR>` and read files with `git show refs/pr/<PR>:<path>`),
   never by checking out the PR in the user's working tree. Read `docs/CODE_REVIEW_PROMPT.md`
   end-to-end and review `origin/<base>...refs/pr/<PR>` under its rules. The worktree has no personal
   files (`profile/`, `config/`, `CLAUDE.local.md` are gitignored); read `examples/` for config/profile shape. Run the test suite in the
   worktree if Python changed (`<repo>/.venv/bin/python -m pytest -q` from the worktree dir).
5. When the Codex job finishes, read `.reviews/pr-<PR>/codex.md`. If it failed, say so in one line
   (point to `.reviews/pr-<PR>/codex.log`) and continue with Claude's findings only.
6. **Merge:**
   - Same file + same root cause = one finding, tagged `Both`. Take the more severe severity only if
     that reviewer's evidence supports it.
   - For each Codex-only finding, verify it yourself against the code. Keep it only if the evidence
     chain holds (tag `Codex`); drop it silently if it does not.
   - Claude-only findings are tagged `Claude`.
   - Order: MUST-FIX, SHOULD-FIX, NITPICK. Renumber.
7. Output findings in the `docs/CODE_REVIEW_PROMPT.md` format, with one added line directly under
   the heading: `**Found by:** Claude / Codex / Both`. If nothing survives, reply exactly `None.`
8. If `--post`: `gh pr comment <PR> --body-file <tmpfile>` with the merged findings, prefixed by
   `## Review (Claude + Codex)`. Otherwise do not touch the PR.
9. Clean up: `git worktree remove --force .reviews/pr-<PR>/wt`. Keep `codex.md` / `codex.log`.

Review only. Do not edit files, commit, push, or resolve threads unless the user then asks for FIX MODE.

## Forbidden response shape

No Summary, Verdict, Questions, Overview, Reviewed surface, Checklist, Recommendation, celebration
prose, or soft labels. Omit medium/low-confidence items entirely.
