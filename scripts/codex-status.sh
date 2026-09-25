#!/usr/bin/env bash
# Non-interactive stand-in for Codex's `/status` (TUI-only): can Codex run right now?
# Usage: scripts/codex-status.sh [PR_NUMBER]
#   With a PR number, first scans .reviews/pr-<N>/codex.log (a stalled or failed /review run).
#   Then checks login and sends a tiny `codex exec` probe (90 s cap).
# Prints one line. Exit: 0 ok | 3 usage limit (line includes "try again at ...") | 4 not logged in | 5 other error/timeout
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
LIMIT_RE='usage limit|rate limit|quota|try again at'
PR="${1:-}"

limit_line() { grep -iE "$LIMIT_RE" | grep -iv '^ *tokens used' | tail -1 | sed 's/^ERROR: *//'; }

if [ -n "$PR" ] && [ -f "$ROOT/.reviews/pr-$PR/codex.log" ]; then
  hit="$(limit_line < "$ROOT/.reviews/pr-$PR/codex.log")"
  if [ -n "$hit" ]; then echo "codex: out of usage (pr-$PR log): $hit"; exit 3; fi
fi

if ! codex login status >/dev/null 2>&1; then
  echo "codex: not logged in (run \`codex login\`)"; exit 4
fi

# perl alarm = portable timeout (macOS has no coreutils `timeout` by default)
probe="$(perl -e 'alarm shift; exec @ARGV' 90 codex exec --ephemeral --sandbox read-only --skip-git-repo-check \
  "Reply with exactly: OK" 2>&1)"
rc=$?
hit="$(printf '%s\n' "$probe" | limit_line)"
if [ -n "$hit" ]; then echo "codex: out of usage: $hit"; exit 3; fi
if [ "$rc" -eq 142 ]; then echo "codex: probe timed out after 90 s (service slow or stuck)"; exit 5; fi
if [ "$rc" -ne 0 ]; then echo "codex: probe failed (exit $rc): $(printf '%s\n' "$probe" | tail -1)"; exit 5; fi
echo "codex: ok (usage available)"
