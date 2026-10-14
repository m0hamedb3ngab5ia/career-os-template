# TASK-036 handoff
Done: SetupCard + TopPicks band (2331a32). Todo: E2E-015-02..04.
Plan: backend POST /api/jobs/{id}/prepare (rc.start("prepare", job_id=...), ticks job); Today gets `prepare_runs` {job_id: {state: running|failed, run_id, cause}} from RunStore attempts (outcome!=ok) / rc.active_run_for;
UI: Prepare/Skip(status skipped, Undo restores `previous` via POST /api/jobs/{id}/status)/Retry on TopPicks cards, outside card Link.
