"""Pipeline steps the UI starts that are not budgeted batches: scout, tracker sync, prune, inbox sync.

`python -m careeros.ui.services.step --root <root> <kind>` runs one step in its own process (so it outlives a UI
restart) and records it like a batch: data/runs/<id>/run.json (kind scout|tracker|prune, trigger manual) + run.log,
so Runs › History shows it. The work itself is the scheduler's (`tick.default_actions`) or the CLI's
(`tracker.sync_all`); nothing is reimplemented. One step of a kind at a time: data/runs/step-<kind>.lock.
Inbox sync is a headless skill call; `service.run_skill` records its own run and holds the runner lock.
SIGTERM (the UI's Cancel) ends the step with stop reason `cancelled`.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.store import RunStore, iso
from careeros.ui.services.runs import Busy

STEP_KINDS = ("scout", "tracker", "prune", "inbox_sync")
LOCK_TTL_S = 3 * 3600  # a dead pid frees it sooner


class StepBusy(Busy):
    def __init__(self, holder: dict[str, Any]):
        super().__init__(holder, f"a {holder.get('note') or 'step'} step is already running")


def step_lock_path(rs: RunStore, kind: str) -> Path:
    return rs.dir / f"step-{kind}.lock"


def default_actions(settings: Settings) -> dict[str, Callable[[], tuple[str, str]]]:
    from careeros.runs import tick
    from careeros.tracker import sync_all

    sched = tick.default_actions(settings)

    def tracker() -> tuple[str, str]:
        out = sync_all(settings)
        return "ok", f"synced {out['synced']} jobs" + (f" ({out['pending']} ops queued, file locked)"
                                                       if out["pending"] else "")

    return {"scout": lambda: sched["scout"]("manual"), "prune": lambda: sched["prune"]("manual"),
            "tracker": tracker}


def run_step(settings: Settings, kind: str, *, actions: dict[str, Callable[[], tuple[str, str]]] | None = None,
             now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> dict[str, Any]:
    """Run scout | tracker | prune once, recorded as a run. Raises StepBusy when one of that kind is running."""
    if kind not in ("scout", "tracker", "prune"):
        raise ValueError(f"unknown step {kind!r}")
    rs = RunStore(settings)
    start = now()
    rid = f"{start.astimezone().strftime('%Y%m%d-%H%M%S')}-{kind}-{os.urandom(2).hex()}"
    try:
        lk = locks.acquire(step_lock_path(rs, kind), owner=f"step:{rid}", ttl_seconds=LOCK_TTL_S, pid=os.getpid(),
                           now=start, note=kind)
    except locks.LockBusy as e:
        raise StepBusy(e.holder) from None
    run = rs.new_run(kind, "manual", {}, start, run_id=rid, step=True)
    rs.log(rid, f"start {kind}")
    status, stop, detail = "done", "completed", ""
    try:
        actions = actions if actions is not None else default_actions(settings)
        result, detail = actions[kind]()
        if result != "ok":
            status, stop = "failed", "error"
    except KeyboardInterrupt:
        stop, detail = "cancelled", "cancelled by signal"
    except Exception as e:  # noqa: BLE001 - recorded on the run; the UI shows it
        status, stop, detail = "failed", "error", f"{type(e).__name__}: {e}"[:500]
    finally:
        end = now()
        run.update(status=status, stop_reason=stop, detail=detail, ended_at=iso(end),
                   duration_s=round((end - start).total_seconds(), 1))
        rs.save_run(run)
        rs.log(rid, f"stop {stop}" + (f": {detail}" if detail else ""))
        locks.release(step_lock_path(rs, kind), lk.token)
    return run


def run_inbox_sync(settings: Settings) -> dict[str, Any]:
    import threading

    from careeros.runs.schedule import load_schedule
    from careeros.runs.service import run_skill

    cancel = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: cancel.set())
    job = load_schedule(settings).jobs["inbox_sync"]
    return run_skill(settings, "inbox_sync", "inbox-sync", mcp_servers=job.mcp_servers,
                     allowed_tools_extra=job.allowed_tools_extra, trigger="manual", cancel=cancel)


def _raise_interrupt(*_: Any) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m careeros.ui.services.step")
    p.add_argument("--root")
    p.add_argument("kind", choices=STEP_KINDS)
    args = p.parse_args(argv)
    settings = Settings.load(Path(args.root) if args.root else None)
    if args.kind == "inbox_sync":
        rec = run_inbox_sync(settings)
    else:
        signal.signal(signal.SIGTERM, _raise_interrupt)
        try:
            rec = run_step(settings, args.kind)
        except StepBusy as e:
            print(str(e), file=sys.stderr)
            return 5
    print(rec["id"])
    return 0 if rec.get("stop_reason") in ("completed", "cancelled") else 1


if __name__ == "__main__":
    sys.exit(main())
