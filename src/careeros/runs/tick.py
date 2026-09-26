"""`careeros tick` (called by launchd every schedule.tick_minutes) and `careeros run catch-up`.

A tick is idempotent: it takes `data/runs/tick.lock` without waiting (a tick already going means this one does
nothing), plans with schedule.plan_tick, runs what is due in order (scout, score, prepare, prune), and records
each job's last run in `data/runs/schedule.json`. A score/prepare run that finds the runner busy stays due for
the next tick. Missed slots go to `data/runs/catch_up.json` (one record) and never run by themselves.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.runner import RunBusy
from careeros.runs.schedule import JOB_KINDS, load_schedule, merge_catch_up, next_runs, plan_tick
from careeros.runs.store import RunStore

Action = Callable[[str], tuple[str, str]]  # trigger -> (status, detail)
TICK_LOCK_SECONDS = 12 * 3600  # a tick that runs score + prepare can take hours; a dead pid frees it sooner


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read(path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write(path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_state(rs: RunStore) -> dict[str, Any]:
    got = _read(rs.dir / "schedule.json")
    return got if isinstance(got, dict) else {"last_tick": None, "jobs": {}}


def load_catch_up(rs: RunStore) -> dict[str, Any] | None:
    got = _read(rs.dir / "catch_up.json")
    return got if isinstance(got, dict) and got.get("kinds") else None


def _save_catch_up(rs: RunStore, rec: dict[str, Any] | None) -> None:
    p = rs.dir / "catch_up.json"
    if rec and rec.get("kinds"):
        _write(p, rec)
    elif p.exists():
        p.unlink()


def default_actions(settings: Settings, echo: Callable[[str], None] = lambda s: None) -> dict[str, Action]:
    """The real work behind each job kind. Tests pass their own."""
    from careeros.runs.config import budget_for, load_runs_config
    from careeros.runs.service import run_batch

    sched = load_schedule(settings)

    def scout(trigger: str) -> tuple[str, str]:
        from careeros.scout import run_scout, sync_to_tracker
        from careeros.store import Store

        store = Store(settings)
        summary = run_scout(settings, store)
        sync_to_tracker(settings, store, summary)
        t = summary.totals
        return "ok", f"fetched={t['fetched']} new={t['new']} stored={t['stored']}"

    def batch(kind: str) -> Action:
        def run(trigger: str) -> tuple[str, str]:
            cfg = load_runs_config(settings)
            rec = run_batch(settings, kind, budget_for(cfg, kind, preset=sched.jobs[kind].preset), cfg=cfg,
                            trigger=trigger, echo=echo)
            return str(rec["stop_reason"]), f"run {rec['id']}"
        return run

    def prune(trigger: str) -> tuple[str, str]:
        from careeros import retention

        from careeros.runs.storage import snapshot_after_prune

        items = retention.plan(settings)
        freed = retention.execute(settings, items)
        snapshot_after_prune(settings, freed)
        return "ok", f"{len(items)} item(s), {retention.human_bytes(freed)} freed"

    def inbox_sync(trigger: str) -> tuple[str, str]:
        from careeros.runs.service import run_skill

        job = sched.jobs["inbox_sync"]
        rec = run_skill(settings, "inbox_sync", "inbox-sync", mcp_servers=job.mcp_servers,
                        allowed_tools_extra=job.allowed_tools_extra, trigger=trigger, echo=echo)
        return str(rec["stop_reason"]), f"run {rec['id']}"

    return {"scout": scout, "inbox_sync": inbox_sync, "score": batch("score"), "prepare": batch("prepare"),
            "prune": prune}


def _run_one(action: Action, trigger: str) -> tuple[str, str]:
    try:
        return action(trigger)
    except RunBusy as e:
        return "busy", str(e)
    except Exception as e:  # noqa: BLE001 - one job failing must not stop the tick or lose the state
        return "error", f"{type(e).__name__}: {e}"[:300]


def tick(settings: Settings, *, now: datetime | None = None, actions: dict[str, Action] | None = None,
         dry_run: bool = False, echo: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    now = now or _utcnow()
    cfg = load_schedule(settings)
    rs = RunStore(settings)
    state = load_state(rs)
    paused = rs.pause_state(now) is not None
    decisions = plan_tick(cfg, state, now, paused=paused)
    out: dict[str, Any] = {"at": now.isoformat(), "dry_run": dry_run, "paused": paused,
                           "decisions": [d.to_dict() for d in decisions], "results": {}}
    if dry_run:
        return {**out, "status": "dry_run"}
    try:
        lk = locks.acquire(rs.dir / "tick.lock", owner="tick", ttl_seconds=TICK_LOCK_SECONDS, pid=os.getpid(),
                           now=now)
    except locks.LockBusy:
        return {**out, "status": "busy"}
    try:
        actions = actions if actions is not None else default_actions(settings, echo)
        jobs = state.setdefault("jobs", {})
        _save_catch_up(rs, merge_catch_up(load_catch_up(rs), decisions, now))
        for d in decisions:
            entry = jobs.setdefault(d.kind, {})
            if d.action == "missed":
                entry.update(last_run=now.isoformat(), last_status="missed", last_detail=d.detail)
            elif d.action == "skip_paused":
                entry.update(last_run=now.isoformat(), last_status="paused", last_detail="runs paused")
            elif d.action == "run":
                echo(f"tick: {d.kind}")
                status, detail = _run_one(actions[d.kind], "schedule")
                out["results"][d.kind] = {"status": status, "detail": detail}
                if status == "busy":
                    entry.update(last_status="busy", last_detail=detail)
                else:
                    entry.update(last_run=now.isoformat(), last_status=status, last_detail=detail)
        state["last_tick"] = now.isoformat()
        _write(rs.dir / "schedule.json", state)
    finally:
        locks.release(rs.dir / "tick.lock", lk.token)
    return {**out, "status": "ok"}


def run_catch_up(settings: Settings, *, actions: dict[str, Action] | None = None, now: datetime | None = None,
                 dismiss: bool = False, echo: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Run each kind in the pending catch-up record once (trigger catch_up; quiet hours do not apply: the
    candidate asked for it). Kinds that found the runner busy stay pending. RuntimeError while paused."""
    now = now or _utcnow()
    rs = RunStore(settings)
    rec = load_catch_up(rs)
    if dismiss:
        _save_catch_up(rs, None)
        return {"dismissed": bool(rec), "ran": [], "left": []}
    if rec is None:
        return {"ran": [], "left": [], "results": {}, "pending": False}
    if rs.pause_state(now):
        raise RuntimeError("runs are paused; `careeros run resume` first")
    actions = actions if actions is not None else default_actions(settings, echo)
    ran, left, results = [], [], {}
    kinds = dict(rec["kinds"])
    for kind in JOB_KINDS:
        if kind not in kinds:
            continue
        echo(f"catch-up: {kind}")
        status, detail = _run_one(actions[kind], "catch_up")
        results[kind] = {"status": status, "detail": detail}
        if status == "busy":
            left.append(kind)
        else:
            ran.append(kind)
            kinds.pop(kind)
    rec["kinds"] = kinds
    _save_catch_up(rs, rec)
    return {"ran": ran, "left": left, "results": results, "pending": bool(kinds)}


def schedule_overview(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    rs = RunStore(settings)
    state = load_state(rs)
    nxt = next_runs(load_schedule(settings), state, now)
    return {"last_tick": state.get("last_tick"), "jobs": state.get("jobs") or {},
            "next": {k: (v.isoformat() if v else None) for k, v in nxt.items()}, "catch_up": load_catch_up(rs),
            "paused": rs.pause_state(now)}
