# Jobs

Table of every tracked posting; user ticks jobs to prepare/apply and changes statuses.

## Sub-features

- `jobs-list` table at `/jobs` (empty state title `No jobs here yet`).
- `jobs-select` per-row checkbox (accessible name `Select <name>`), header `Select all shown jobs`.
- `jobs-status` status per job via `careeros job status <id> <status>`; valid values: `STATUSES` in `src/careeros/models.py`.
- `jobs-detail` `/jobs/<jobId>` cards (score, posting, documents, `Fill application`).

## How to get to it (user POV)

- Sidebar `Jobs`; header search `Search jobs and companies`.

## Driving it with browser MCP + curl

Preconditions: baseline plus a seeded posting (scaffolding, removed by cleanup): `mkdir -p data/jobs/_example && cp tests/fixtures/example_posting.json data/jobs/_example/posting.json`, then restart the UI or run it with `--reindex`. Not yet proven; confirm the dir layout against `src/careeros/ui/services/jobs.py` `job_dir_for`.

- **List.** `navigate /jobs`; row `Ledgerline` appears.
- **Select.** Click checkbox `Select ...`; `POST /api/jobs/select`; read back with `careeros jobs list` or `GET /api/jobs`.
- **Proof.** Page text + API row showing selected.

## Gotchas

- New postings start unticked (REQ-104); prepare/apply act only on ticked jobs.
- The offline copy has no scout data; do not run `careeros scout` (network).
