# Today

The landing page: what needs the user now, running batches, the next step and recent runs.

## Sub-features

- `today-needs` task list (`Nothing needs you` when empty) with mark-done.
- `today-next` next-step card (starts from readiness).
- `today-runs` run status (`aria-label="Runs and pipeline"`), scout progress (`aria-label="Scout progress"`).

## How to get to it (user POV)

- Open `/` or sidebar `Today`.

## Driving it with browser MCP + curl

Preconditions: baseline from `README.md`.

- **Load.** `navigate http://127.0.0.1:8799/`, `Skip tour`, `get_page_text`: heading `Today`.
- **Seed a task.** `.venv/bin/careeros action add "verify task" --type <t> --needs anytime` (types: `ACTION_TYPES` in `src/careeros/models.py`), reload; task appears; `Mark done` circle moves it; `.../careeros action list` agrees. Not yet proven.
- **Proof.** Page text + `GET /api/today` body.

## Gotchas

- Fresh copy has no tasks; the empty state is the baseline.
- `action add` writes `data/`, removed by cleanup.
