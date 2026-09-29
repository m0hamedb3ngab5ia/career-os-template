"""Pipeline steps the UI starts that are not budgeted batches: scout, tracker sync, prune, inbox sync, one job's QA.

`python -m careeros.ui.services.step --root <root> <kind>` runs one step in its own process (so it outlives a UI
restart) and records it like a batch: data/runs/<id>/run.json (kind scout|tracker|prune, trigger manual) + run.log,
so Runs › History shows it. The work itself is the scheduler's (`tick.default_actions`) or the CLI's
(`tracker.sync_all`); nothing is reimplemented. One step of a kind at a time: data/runs/step-<kind>.lock.
Scout and prune also hold the pipeline lock (data/runs/runner.lock, owner step:<id>, `locks.pipeline_lock`), so
they never overlap a batch (losing that race records a failed run, stop reason `busy`); the tracker sync writes atomically per op and may run beside one.
The scout step's own tracker sync runs after the pipeline lock is released (like the scheduler's scout), so a tracker
file held open in Excel never keeps a batch or a tick waiting; a sync error still fails the step, as it does there.
Inbox sync is a headless skill call; `service.run_skill` records its own run and holds the runner lock.
The step's stdout/stderr lines go to its run.log, so the Runs log tail streams them.
SIGTERM (the UI's Cancel) ends the step with stop reason `cancelled` and discards its partial output: a cancelled
scout removes the job folders it created and restores seen/history, also when cancelled during its tracker sync;
QA writes nothing until it finishes (its result lands on run.json `result`). A Stop that lands before the step
holds its lock leaves data/runs/ui/cancel-<id>; the step finds it once locked and records `cancelled` without running.
"""
from __future__ import annotations

import argparse
import io
import os
import signal
import sys
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Union

from careeros.config import Settings
from careeros.runs import locks
from careeros.runs.store import RunStore, iso
from careeros.ui.services.runs import Busy

STEP_KINDS = ("scout", "tracker", "prune", "inbox_sync", "qa")
LOCK_TTL_S = 3 * 3600  # a dead pid frees it sooner
PIPELINE_STEPS = ("scout", "prune")  # steps that also take the pipeline lock (never beside a batch)
# (status, detail), or (status, detail, after): `after` runs once the pipeline lock is released (scout's tracker sync)
StepResult = Union[tuple[str, str], tuple[str, str, Callable[[], Any]]]
StepAction = Callable[[], StepResult]


class StepBusy(Busy):
    def __init__(self, holder: dict[str, Any]):
        super().__init__(holder, f"a {holder.get('note') or 'step'} step is already running")


class _RunLogWriter(io.TextIOBase):
    """stdout/stderr of a step, one run.log line per printed line, so the Runs log tail shows progress live."""

    def __init__(self, rs: RunStore, run_id: str):
        self.rs, self.run_id, self.buf = rs, run_id, ""

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:
        self.buf += s
        *lines, self.buf = self.buf.split("\n")
        for line in lines:
            if line.strip():
                self.rs.log(self.run_id, line.rstrip())
        return len(s)

    def flush(self) -> None:
        if self.buf.strip():
            self.rs.log(self.run_id, self.buf.rstrip())
        self.buf = ""


def step_lock_path(rs: RunStore, kind: str) -> Path:
    return rs.dir / f"step-{kind}.lock"


def _snapshot(paths: list[Path]) -> Callable[[], None]:
    """Restore these files to their current bytes (a missing one is removed again)."""
    saved = {p: p.read_bytes() if p.exists() else None for p in paths}

    def restore() -> None:
        for p, data in saved.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)
    return restore


def default_actions(settings: Settings, job_id: str | None = None) -> dict[str, StepAction]:
    from careeros.runs import tick
    from careeros.tracker import sync_all

    sched = tick.default_actions(settings)

    def scout() -> StepResult:
        """The scheduler's scout split in two: run_scout under the step's pipeline lock, the sync after it."""
        from careeros.scout import run_scout, sync_to_tracker
        from careeros.store import Store

        store = Store(settings)
        before = {d.name for d in store.jobs_dir.iterdir()}
        restore = _snapshot([store.seen_file, store.history_file])

        def discarding(fn: Callable[[], Any]) -> Any:
            try:
                return fn()
            except KeyboardInterrupt:  # Cancel: discard what this scout stored so far
                import shutil

                for d in store.jobs_dir.iterdir():
                    if d.name not in before and d.is_dir():
                        shutil.rmtree(d, ignore_errors=True)
                restore()
                raise
        summary = discarding(lambda: run_scout(settings, store))
        return "ok", tick.scout_detail(summary), \
            lambda: discarding(lambda: sync_to_tracker(settings, store, summary))

    def tracker() -> tuple[str, str]:
        out = sync_all(settings)
        return "ok", f"synced {out['synced']} jobs" + (f" ({out['pending']} ops queued, file locked)"
                                                       if out["pending"] else "")

    def qa() -> tuple[str, str, Callable[[], Any]]:
        from careeros.ui.services.job_actions import rerun_qa

        r = rerun_qa(settings, str(job_id))
        s = r.get("summary") or {}
        return "ok", f"{'pass' if r.get('pass') else 'fail'}: {s.get('hard_fail', 0)} hard, {s.get('soft_fail', 0)} soft", \
            lambda: r

    return {"scout": scout, "prune": lambda: sched["prune"]("manual"),
            "tracker": tracker, "qa": qa}


def run_step(settings: Settings, kind: str, *, actions: dict[str, StepAction] | None = None,
             now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), job_id: str | None = None,
             run_id: str | None = None) -> dict[str, Any]:
    """Run scout | tracker | prune once, recorded as a run. Raises StepBusy when one of that kind is running.
    A scout/prune that finds the pipeline lock held (a batch started after the UI's check) is recorded as a
    failed run with stop reason `busy` (main exits 5)."""
    if kind not in ("scout", "tracker", "prune", "qa"):
        raise ValueError(f"unknown step {kind!r}")
    rs = RunStore(settings)
    start = now()
    rid = run_id or f"{start.astimezone().strftime('%Y%m%d-%H%M%S')}-{kind}-{os.urandom(2).hex()}"
    with ExitStack() as held:  # releases whatever was taken, even when recording the run raises
        try:
            lk = locks.acquire(step_lock_path(rs, kind), owner=f"step:{rid}", ttl_seconds=LOCK_TTL_S,
                               pid=os.getpid(), now=start, note=kind)
        except locks.LockBusy as e:
            raise StepBusy(e.holder) from None
        held.callback(locks.release, step_lock_path(rs, kind), lk.token)
        busy: locks.LockBusy | None = None
        pipe = held.enter_context(ExitStack())  # closed early: the `after` part runs without the pipeline lock
        if kind in PIPELINE_STEPS:
            try:
                pipe.enter_context(locks.pipeline_lock(settings, f"step:{rid}", note=kind, wait_s=0))
            except locks.LockBusy as e:  # lost the race after the UI's pre-spawn check: record why nothing ran
                busy = e
        run = rs.new_run(kind, "manual", {}, start, run_id=rid, step=True, **({"job_id": job_id} if job_id else {}))
        rs.log(rid, f"start {kind}")
        status, stop, detail = "done", "completed", ""
        out = _RunLogWriter(rs, rid)
        try:
            if (rs.dir / "ui" / f"cancel-{rid}").exists():  # Stop pressed before this step held its lock
                raise KeyboardInterrupt
            if busy is not None:
                status, stop, detail = "failed", "busy", str(busy)[:500]
            else:
                actions = actions if actions is not None else default_actions(settings, job_id)
                with redirect_stdout(out), redirect_stderr(out):
                    result, detail, *after = actions[kind]()
                    pipe.close()
                    if result == "ok" and after:
                        value = after[0]()
                        if kind == "qa":
                            run["result"] = value
                if result != "ok":
                    status, stop = "failed", "error"
        except KeyboardInterrupt:
            stop, detail = "cancelled", "cancelled by signal"
        except Exception as e:  # noqa: BLE001 - recorded on the run; the UI shows it
            status, stop, detail = "failed", "error", f"{type(e).__name__}: {e}"[:500]
        finally:
            out.flush()
            end = now()
            run.update(status=status, stop_reason=stop, detail=detail, ended_at=iso(end),
                       duration_s=round((end - start).total_seconds(), 1))
            rs.save_run(run)
            rs.log(rid, f"stop {stop}" + (f": {detail}" if detail else ""))
    return run


def run_inbox_sync(settings: Settings) -> dict[str, Any]:
    import threading

    from careeros.runs.schedule import load_schedule
    from careeros.runs.service import run_skill

    cancel = threading.Event()
    old = signal.signal(signal.SIGTERM, lambda *_: cancel.set())  # SIGTERM = the UI's Cancel: stop cleanly
    try:
        job = load_schedule(settings).jobs["inbox_sync"]
        return run_skill(settings, "inbox_sync", "inbox-sync", mcp_servers=job.mcp_servers,
                         allowed_tools_extra=job.allowed_tools_extra, trigger="manual", cancel=cancel)
    finally:
        signal.signal(signal.SIGTERM, old)


def _raise_interrupt(*_: Any) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m careeros.ui.services.step")
    p.add_argument("--root")
    p.add_argument("kind", choices=STEP_KINDS)
    p.add_argument("--job")
    p.add_argument("--run-id")
    args = p.parse_args(argv)
    if args.kind == "qa" and not args.job:
        p.error("qa needs --job")
    settings = Settings.load(Path(args.root) if args.root else None)
    if args.kind == "inbox_sync":
        rec = run_inbox_sync(settings)
    else:
        signal.signal(signal.SIGTERM, _raise_interrupt)
        try:
            rec = run_step(settings, args.kind, job_id=args.job, run_id=args.run_id)
        except Busy as e:  # StepBusy, or a batch holds the pipeline lock
            if args.run_id:  # JSON, so RunControl.start_error can tell the UI why the run never started
                import json

                print(json.dumps({"error": str(e)}))
            else:
                print(str(e), file=sys.stderr)
            return 5
    print(rec["id"])
    if rec.get("stop_reason") == "busy":
        print(rec.get("detail", ""), file=sys.stderr)
        return 5
    return 0 if rec.get("stop_reason") in ("completed", "cancelled") else 1


if __name__ == "__main__":
    sys.exit(main())
