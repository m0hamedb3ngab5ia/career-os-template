# Jobs

Table of every tracked posting; user ticks jobs to prepare/apply and changes statuses.

## Sub-features

- `jobs-list` table at `/jobs` (empty state title `No jobs here yet`).
- `jobs-select` per-row checkbox (accessible name `Select <name>`), header `Select all shown jobs`.
- `jobs-status` status per job via `careeros job status <id> <status>`; valid values: `STATUSES` in `src/careeros/models.py`.
- `jobs-detail` `/jobs/<jobId>` cards (score, posting, documents, `Fill application`).

## How to get to it (user POV)

- Sidebar `Jobs`; header search `Search jobs and companies`.

## Driving it (user mode, Playwright)

Preconditions: baseline plus a seeded posting (scaffolding, removed by cleanup): `mkdir -p data/jobs/example-1 && sed 's/"_example"/"example-1"/' tests/fixtures/example_posting.json > data/jobs/example-1/posting.json` (ids starting with `_` are hidden), then restart the UI or run it with `--reindex`. Not yet proven; confirm the dir layout against `src/careeros/ui/services/jobs.py` `job_dir_for`.

- **List.** `page.goto("/jobs")`; row `Ledgerline` appears.
- **Select.** Click checkbox `Select ...`; `POST /api/jobs/select`; read back with `careeros jobs list` or `GET /api/jobs`.
- **Proof.** Page text + API row showing selected.

## Driving it (dev mode, API)

`curl -s 127.0.0.1:8799/api/jobs`; `curl -s -X POST -H 'X-CareerOS: 1' -H 'Content-Type: application/json' -d '{...}' 127.0.0.1:8799/api/jobs/select` (body shape: `src/careeros/ui/`); `careeros jobs list`.

## UX checks

- One obvious next action: tick, then prepare (primary action obvious).
- Selection state visible; bulk select labelled.
- Empty state `No jobs here yet` offers the fix (scout/seed).
- Checkbox and row targets large enough, keyboard reachable.
- Steps to first value (TTV).

## Gotchas

- New postings start unticked (REQ-104); prepare/apply act only on ticked jobs.
- The offline copy has no scout data; do not run `careeros scout` (network).
