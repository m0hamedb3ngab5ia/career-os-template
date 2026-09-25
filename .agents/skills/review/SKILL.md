---
name: review
description: CodeRabbit-style REVIEW ONLY of a career-os GitHub PR against its base branch using docs/CODE_REVIEW_PROMPT.md. Use when the user asks to $review or /review a PR number.
---

# Review a PR

The user gives a PR number (`$review 12`). If none, ask and stop.

1. `gh pr view <PR> --json number,title,body,baseRefName,headRefName,url`
2. Base = `baseRefName` (PRs are often stacked; do not assume `main`).
3. `git fetch origin <base> pull/<PR>/head:refs/pr/<PR>` and review
   `git diff --find-renames --find-copies origin/<base>...refs/pr/<PR>`, reading full files with
   `git show refs/pr/<PR>:<path>`. Do not check out over the user's working tree.
4. Read `docs/CODE_REVIEW_PROMPT.md` end-to-end and follow it: REVIEW ONLY, evidence standard,
   severity, career-os invariants, Output format.
   There are no personal files in a review checkout; read `examples/config/` and `examples/profile/`.
5. Reply with finding blocks only, or exactly `None.`

Headless equivalent (used by Claude's `/review`): `scripts/review.sh <PR>`.
