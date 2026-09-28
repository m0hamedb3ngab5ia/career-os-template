# HANDOFF — PR #67 codex fixes

Done:
- Finding #2 (SHOULD-FIX, cache invalidation): added `["jobs-facets"]` to
  `ui/src/api/events.ts` job-change invalidations; updated `events.test.tsx`.
- Finding #4 (SHOULD-FIX, a11y focus): `HeaderFilterMenu.tsx` `close()` now
  restores focus to the trigger button; `apply`/`clear`/sort buttons all
  route through `close()`.
- Finding #3 (NIT, backslash round-trip): replaced regex split/escape in
  `urlState.ts` with a manual `splitEscaped` scanner + backslash-escaping
  `writeFilter`; added round-trip test in `urlState.test.ts`.
- Tests: `npm test -- --run` → 411/411 passed. `npm run typecheck` → clean.

Skipped:
- Finding #1 (SHOULD-FIX, missing header controls for category/qa_passed/
  closes_at): backend + urlState.FILTERS already support all three; not
  implemented — ran out of tool-call budget (hook hard-stopped exploration
  at 30 calls) before touching `cells.tsx`/`JobsPage.tsx`. Needs 3 new
  `Column` entries in `ui/src/features/jobs/cells.tsx` (category: humanize
  cell; qa_passed: Passed/Failed cell; closes_at: formatDate cell) + adding
  the new keys to `HIDEABLE` in `urlState.ts`. Est. ~40-60 lines, should fit
  the ~100-line cap.

Not done:
- `npm run build` not run: sandbox Node is 26, repo requires Node 22
  (`scripts/check-node.mjs`); the required `npx -p node@22 -- npm run build`
  invocation was rejected by the usage-guard hook (pattern only allows a
  literal `npm run build` start). Static bundle in
  `src/careeros/ui/static/` is therefore NOT rebuilt despite ui/src changes.
  Next agent: run `cd ui && npx -p node@22 -- npm run build` and commit the
  bundle.
- PII grep not run this session (hook blocked grep as "exploration");
  changes are UI logic only, no personal data touched — should be safe but
  re-run `git diff origin/main | grep -inE 'barclays|bengabsia|mohamed|stevens|ansary|whippany'`
  to confirm empty before merge.

Files changed: ui/src/api/events.ts, ui/src/api/events.test.tsx,
ui/src/features/jobs/HeaderFilterMenu.tsx, ui/src/features/jobs/urlState.ts,
ui/src/features/jobs/urlState.test.ts
