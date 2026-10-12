# career-os verification map

Maintained source for verifying user-facing behavior. Read it before driving, then use the feature file as the recipe.

## Baseline preconditions

- Pick mode (`user` default, `dev`; see `../SKILL.md`). Launch per `../SKILL.md` on port 8799 from the checkout under test, after `careeros init` (fictional candidate).
- `claude` is NOT on the instance's PATH: LLM steps will fail fast (`doctor_failed`), by design.
- Run Doctor; require our PID on 8799. Never drive port 8765 or any instance you did not start.
- Evidence dir `$EV` exists (see SKILL.md Evidence).

## Driving conventions

- Prefer ARIA roles/names and visible text over CSS or coordinates. Dismiss the tour (`Skip tour`) on first load.
- Dev mode: API writes need `X-CareerOS: 1`. Reads are open.
- Start from the baseline state; undo mutations (or re-run cleanup) afterwards. Do not remove evidence.

## Proof and skip reporting

- Capture the user action and the resulting state; UI text plus a read-only API/disk view of the stored value.
- Record feature ID and entry point with every artifact.
- Report an unreachable path with the attempted command and unmet precondition. A skipped LLM or network step is "not proven", never "verified through another path".

## Features

- [Today](./today.md) to-do list and next step.
- [Jobs](./jobs.md) table, selection, statuses (needs seeded postings).
- [Profile › Résumés](./profile-resumes.md) upload, ATS data, review feedback, versions. PROVEN (user mode): upload via page, list, files on disk.
- [Settings](./settings.md) sections and save bar.
- [Apply fill](./apply-fill.md) stage a form in Chromium (documented, not provable offline).
