"""Run state shared by `careeros run list|show|status` and the UI: a run's live state and the status summary."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.store import RunStore

STATUS_QUEUE_KINDS = ("score", "prepare")


def run_state(rs: RunStore, run: dict[str, Any], alive=locks.pid_alive) -> str:
    """run.json `status`, except a `running` run whose process no longer holds its lock: interrupted. Batches hold
    the runner lock (owner run:<id>); UI steps (scout, tracker, prune) hold data/runs/step-<kind>.lock (step:<id>)."""
    if run.get("status") != "running":
        return str(run.get("status"))
    for path, owner in ((rs.runner_lock_path, f"run:{run['id']}"),
                        (rs.dir / f"step-{run.get('kind')}.lock", f"step:{run['id']}")):
        held = locks.status(path, alive=alive)
        if held.get("state") == "held" and held.get("owner") == owner:
            return "running"
    return "interrupted"


def status_data(s: Settings) -> dict[str, Any]:
    """What is running, pause, the last run of each kind, the live top 5 per queue, the cap and the schedule."""
    from careeros.runs.config import KINDS, load_runs_config
    from careeros.runs.policy import AutoSubmitPolicy, current_cap
    from careeros.runs.runner import select_candidates
    from careeros.runs.tick import load_catch_up, schedule_overview

    rs = RunStore(s)
    now = datetime.now(timezone.utc)
    held = locks.status(rs.runner_lock_path)
    cfg = load_runs_config(s)
    last, nxt = {}, {}
    for kind in KINDS:
        prev = rs.list_runs(kind=kind, limit=1)
        last[kind] = ({k: prev[0].get(k) for k in ("id", "trigger", "stop_reason", "started_at", "ended_at",
                                                    "counters")} | {"state": run_state(rs, prev[0])}) if prev else None
    for kind in STATUS_QUEUE_KINDS:
        ranked, _ = select_candidates(s, kind, cfg, now)
        nxt[kind] = [{k: r[k] for k in ("job_id", "company", "title", "score", "why")} for r in ranked[:5]]
    auto = AutoSubmitPolicy.from_config(cfg.raw)
    return {"running": held if held.get("state") == "held" else None, "paused": rs.pause_state(now),
            "preset": cfg.preset, "last": last, "next": nxt, "cap": current_cap(s),
            "auto_submit": {"enabled": auto.enabled, "allow": auto.allow, "manual": auto.manual},
            "catch_up": load_catch_up(rs), "schedule": schedule_overview(s)["next"]}
