# Apply fill

On a job page the user clicks `Fill application`; the app stages the ATS form in a detached Chromium via Playwright, reads values back, never submits.

## Sub-features

- `fill-plan` `careeros apply plan <job_id>` builds `fill_plan.json` (Greenhouse; network).
- `fill-open` button `Fill application` / `Refill application` / `Retry fill` / `Open application` on `/jobs/<id>`.

## How to get to it (user POV)

- `/jobs/<id>` page, Fill application card.

## Driving it (user mode, Playwright)

Preconditions: network, `pip install -e '.[fast-apply]'`, `playwright install chromium`, a prepared job. NOT PROVABLE in the isolated offline copy: document only. Report as "not proven" with the unmet precondition.

- **If ever run.** `curl -s -X POST -H 'X-CareerOS: 1' 127.0.0.1:8799/api/jobs/<id>/application/open`, check `data/jobs/<id>/fill_summary.json` and the screenshot; verify nothing was submitted.

## Driving it (dev mode, API)

`curl -s -X POST -H 'X-CareerOS: 1' 127.0.0.1:8799/api/jobs/<id>/application/open`; check `data/jobs/<id>/fill_summary.json`. Not provable offline.

## UX checks

- One obvious next action on the Fill card (label matches state).
- Wait shows progress while the form stages.
- Failure says what to fix (`Retry fill`).
- Nothing submitted without an explicit user step.

## Gotchas

- Opens a real browser and the network; the filled tab stays open (CDP 127.0.0.1:9223 by default). Never run against a live posting without the user.
