#!/usr/bin/env bash
# Run the Codex half of /review for one PR, headless, in an isolated worktree.
# Usage: scripts/review.sh <PR_NUMBER>
# Output: .reviews/pr-<N>/codex.md (findings only, per docs/CODE_REVIEW_PROMPT.md)
set -euo pipefail

PR="${1:?usage: scripts/review.sh <PR_NUMBER>}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

META="$(gh pr view "$PR" --json number,title,body,baseRefName,headRefName,url)"
BASE="$(jq -r .baseRefName <<<"$META")"
TITLE="$(jq -r .title <<<"$META")"
BODY="$(jq -r .body <<<"$META")"

OUT_DIR="$ROOT/.reviews/pr-$PR"
WT="$OUT_DIR/wt"
mkdir -p "$OUT_DIR"

git fetch -q origin "$BASE" "pull/$PR/head:refs/pr/$PR" --force
if [ -d "$WT" ]; then git worktree remove --force "$WT"; fi
git worktree add -q --detach "$WT" "refs/pr/$PR"

PROMPT="$(cat <<PROMPT_EOF
You are the Codex reviewer for career-os PR #$PR.
PR title: $TITLE
PR body:
$BODY

Base branch: origin/$BASE. Review ONLY the committed PR changes:
  git diff --find-renames --find-copies origin/$BASE...HEAD

This worktree has no personal files (profile/, config/, CLAUDE.local.md are gitignored); read
examples/config/ and examples/profile/ for their shape.
Read docs/CODE_REVIEW_PROMPT.md end-to-end and follow it exactly: REVIEW ONLY mode, evidence
standard, severity rules, career-os invariants, and the Output format. Do not edit files.
Reply with finding blocks only, or exactly "None."
PROMPT_EOF
)"

codex exec -C "$WT" --sandbox read-only --ephemeral -o "$OUT_DIR/codex.md" "$PROMPT" > "$OUT_DIR/codex.log" 2>&1 \
  || { echo "codex review failed; see $OUT_DIR/codex.log" >&2; exit 1; }

echo "$OUT_DIR/codex.md"
