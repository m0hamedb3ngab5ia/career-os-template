# Today

The landing page: what needs the user now, running batches, the next step and recent runs.

## Sub-features

- `today-needs` task list (`Nothing needs you` when empty) with mark-done.
- `today-next` next-step card (starts from readiness).
- `today-runs` run status (`aria-label="Runs and pipeline"`), scout progress (`aria-label="Scout progress"`).

## How to get to it (user POV)

- Open `/` or sidebar `Today`.

## Driving it (user mode, Playwright)

Preconditions: baseline from `README.md`.

- **Load.** `page.goto("/")`, skip tour; heading `Today`.
- **Seed a task.** `.venv/bin/careeros action add "verify task" --type <t> --needs anytime` (types: `ACTION_TYPES` in `src/careeros/models.py`), reload; task appears; `Mark done` circle moves it; `.../careeros action list` agrees. Not yet proven.
- **Proof.** Page text + `GET /api/today` body.

## Driving it (dev mode, API)

`curl -s 127.0.0.1:8799/api/today`; seed with `careeros action add ...`; compare `careeros action list`.

## UX checks

- One obvious next action on the screen (P: primary action obvious).
- Empty state says what to do, not just `Nothing needs you`.
- Mark-done feedback is immediate.
- Steps from open to first value (TTV): count clicks in `steps.jsonl`.

## Gotchas

- Fresh copy has no tasks; the empty state is the baseline.
- `action add` writes `data/`, removed by cleanup.
