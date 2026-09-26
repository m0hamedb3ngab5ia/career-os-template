"""Unattended runs: Python picks the jobs and enforces the budgets; each job is one headless skill call.

- `config.py`   `pipeline.yaml: runs` + `llm` (budgets / presets, ranking weights, headless command), validated.
- `locks.py`    lock files with pid + expiry: one global runner lock, one lock per job.
- `ranking.py`  which jobs go next and why (freshness, dream company, deadline; fit for prepare). No LLM.
- `headless.py` builds the `claude -p` command, streams its stream-json output, validates the skill's RESULT
                line and classifies the outcome (ok, usage_limit, auth_required, permission_denied, timeout, ...).
- `store.py`    run history in files: data/runs/<id>/run.json + attempts/NNN.json + run.log.
- `runner.py`   the loop: preflight, select, invoke, record, stop.
"""
